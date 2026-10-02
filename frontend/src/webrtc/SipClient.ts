// SipClient: the only place that talks SIP/WebRTC. React consumes it via SipContext.
//
//   createSipClient(config, events) -> MockSipClient | RealSipClient
//
// Both implement the same interface (connect, disconnect, call, answer, reject,
// hangup, mute, unmute, hold, resume, sendDtmf) and emit the same events
// (onRegistered, onRegistrationFailed, onIncomingCall, onCallRinging,
// onCallAnswered, onCallEnded, onCallFailed, ...). Only one call at a time.
//
// Audio flows browser <-> FreePBX directly (SIP over WSS + SRTP). Never via FastAPI.

import {
  Invitation,
  Inviter,
  Registerer,
  RegistererState,
  SessionState,
  UserAgent,
  type Session,
  type Web,
} from "sip.js";
import type { IncomingResponse } from "sip.js/lib/core";
import { CALLED_NUMBER_HEADERS, validateSipConfig } from "./config";
import type {
  CallEndReason,
  RegistrationState,
  SipCall,
  SipClient,
  SipClientEvents,
  SipConfig,
  SipMode,
} from "./types";

const OUTBOUND_RING_TIMEOUT_MS = 60_000;
const INBOUND_RING_TIMEOUT_MS = 45_000;
const REGISTRATION_TIMEOUT_MS = 15_000;

export class SipError extends Error {}

let sequence = 0;
function newCallId(): string {
  sequence += 1;
  return `call-${Date.now().toString(36)}-${sequence}`;
}

/** Turn a SIP final response into a CRM-friendly end reason + message. */
export function describeSipStatus(code: number, reason = ""): { endReason: CallEndReason; message: string } {
  const phrase = `${code}${reason ? ` ${reason}` : ""}`;
  if ([486, 600, 603].includes(code)) return { endReason: "rejected", message: `Call declined (${phrase})` };
  if ([408, 480, 487].includes(code)) return { endReason: "missed", message: `No answer (${phrase})` };
  if (code === 401 || code === 407) return { endReason: "failed", message: `Authentication required by PBX (${phrase}) - check SIP credentials` };
  if (code === 403) return { endReason: "failed", message: `Forbidden (${phrase}) - extension not allowed to call this number` };
  if (code === 404 || code === 484) return { endReason: "failed", message: `Number not found (${phrase}) - check dial format / outbound route` };
  if (code === 488) return { endReason: "failed", message: `Codec mismatch (${phrase}) - enable Opus/G.711 and WebRTC on the extension` };
  if (code === 503) return { endReason: "failed", message: `Service unavailable (${phrase}) - trunk or route down` };
  return { endReason: "failed", message: `Call failed (${phrase})` };
}

/** Ask for the microphone up front so permission problems give a clear error. */
export async function ensureMicrophone(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new SipError("Microphone access needs a secure page (https:// or http://localhost).");
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    const name = (error as DOMException).name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new SipError("Microphone permission denied. Allow microphone access for this site and try again.");
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") {
      throw new SipError("No microphone found. Connect a headset or microphone.");
    }
    if (name === "NotReadableError") {
      throw new SipError("Microphone is busy or blocked by another application.");
    }
    throw new SipError(`Cannot access microphone: ${(error as Error).message}`);
  }
}

// ============================================================================ base
abstract class BaseSipClient implements SipClient {
  abstract readonly mode: SipMode;
  abstract readonly supportsHold: boolean;
  protected registration: RegistrationState = "disconnected";
  protected current: SipCall | null = null;
  protected remoteAudio: HTMLAudioElement | null = null;
  private timers = new Set<ReturnType<typeof setTimeout>>();

  constructor(protected events: SipClientEvents) {}

  abstract connect(): Promise<void>;
  abstract disconnect(): Promise<void>;
  abstract call(target: string, displayNumber?: string): Promise<SipCall>;
  abstract answer(): Promise<void>;
  abstract reject(): Promise<void>;
  abstract hangup(): Promise<void>;
  abstract mute(): void;
  abstract unmute(): void;
  abstract hold(): Promise<void>;
  abstract resume(): Promise<void>;
  abstract sendDtmf(digit: string): void;

  attachRemoteAudio(element: HTMLAudioElement | null): void {
    this.remoteAudio = element;
  }

  protected setRegistration(state: RegistrationState, error?: string): void {
    this.registration = state;
    this.events.onRegistrationStateChanged?.(state, error);
    if (state === "registered") this.events.onRegistered?.();
    if (state === "failed") this.events.onRegistrationFailed?.(error ?? "Registration failed");
  }

  protected assertCanCall(): void {
    if (this.registration !== "registered") throw new SipError("Softphone is not registered with the PBX.");
    if (this.current) throw new SipError("Already on a call. Hang up first.");
  }

  protected newCall(partial: Pick<SipCall, "direction" | "remoteNumber"> & Partial<SipCall>): SipCall {
    return { id: newCallId(), state: "idle", muted: false, held: false, startedAt: Date.now(), ...partial };
  }

  /** Update the active call and return a snapshot (callers emit events). */
  protected update(patch: Partial<SipCall>): SipCall | null {
    if (!this.current) return null;
    this.current = { ...this.current, ...patch };
    return { ...this.current };
  }

  protected emitUpdated(patch: Partial<SipCall>): void {
    const call = this.update(patch);
    if (call) this.events.onCallUpdated?.(call);
  }

  /** Terminal transition; emits onCallEnded / onCallFailed exactly once. */
  protected finish(reason: CallEndReason, details: { error?: string; statusCode?: number } = {}): void {
    if (!this.current) return;
    const failed = reason === "failed";
    const call: SipCall = {
      ...this.current,
      state: failed ? "failed" : "ended",
      endReason: reason,
      endedAt: Date.now(),
      error: details.error ?? this.current.error,
      statusCode: details.statusCode ?? this.current.statusCode,
    };
    this.current = null;
    this.clearTimers();
    this.cleanupMedia();
    if (failed) this.events.onCallFailed?.(call, call.error ?? "Call failed");
    else this.events.onCallEnded?.(call);
  }

  protected later(ms: number, fn: () => void): void {
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      fn();
    }, ms);
    this.timers.add(timer);
  }

  protected clearTimers(): void {
    this.timers.forEach(clearTimeout);
    this.timers.clear();
  }

  protected cleanupMedia(): void {
    if (this.remoteAudio) {
      this.remoteAudio.pause();
      this.remoteAudio.srcObject = null;
    }
  }
}

// ============================================================================ mock
/**
 * Simulates a registered extension. No network traffic.
 *
 * Outbound test numbers (by last digits):
 *   ...0000 -> fails (503)      ...1111 -> no answer (missed)
 *   ...2222 -> declined (486)   anything else -> answered; remote hangs up after 60s
 */
export class MockSipClient extends BaseSipClient {
  readonly mode = "mock" as const;
  readonly supportsHold = true;

  async connect(): Promise<void> {
    this.setRegistration("connecting");
    await new Promise((resolve) => setTimeout(resolve, 600));
    this.setRegistration("registered");
  }

  async disconnect(): Promise<void> {
    if (this.current) await this.hangup();
    this.setRegistration("disconnected");
  }

  async call(target: string, displayNumber?: string): Promise<SipCall> {
    this.assertCanCall();
    this.current = this.newCall({
      direction: "outbound",
      remoteNumber: displayNumber || target,
      sipCallId: `mock-${Math.random().toString(36).slice(2, 12)}@mock-pbx`,
      state: "connecting",
    });
    const snapshot = { ...this.current };
    this.later(400, () => {
      const call = this.update({ state: "calling" });
      if (call) this.events.onCallStarted?.(call);
      if (target.endsWith("0000")) {
        this.later(1500, () => this.finish("failed", { statusCode: 503, error: describeSipStatus(503, "Service Unavailable").message }));
        return;
      }
      this.later(1200, () => {
        const ringing = this.update({ state: "ringing" });
        if (ringing) this.events.onCallRinging?.(ringing);
        if (target.endsWith("1111")) {
          this.later(8000, () => this.finish("missed", { statusCode: 480, error: "No answer (480 Temporarily Unavailable)" }));
        } else if (target.endsWith("2222")) {
          this.later(2500, () => this.finish("rejected", { statusCode: 486, error: "Call declined (486 Busy Here)" }));
        } else {
          this.later(2500, () => {
            const answered = this.update({ state: "answered", answeredAt: Date.now() });
            if (answered) this.events.onCallAnswered?.(answered);
            this.later(60_000, () => this.finish("completed")); // remote party hangs up
          });
        }
      });
    });
    return snapshot;
  }

  /** Mock-only: pretend FreePBX sent us an INVITE. */
  simulateIncomingCall(from: string, calledNumber?: string, displayName?: string): void {
    if (this.registration !== "registered") throw new SipError("Softphone is not registered.");
    const call = this.newCall({
      direction: "inbound",
      remoteNumber: from,
      remoteDisplayName: displayName,
      calledNumber,
      sipCallId: `mock-${Math.random().toString(36).slice(2, 12)}@mock-pbx`,
      state: "incoming",
    });
    if (this.current) {
      // Same behaviour as real mode: auto-reject with 486 and report it.
      this.events.onCallEnded?.({ ...call, state: "ended", endReason: "busy_rejected", endedAt: Date.now(), statusCode: 486, error: "Auto-rejected: agent already on a call" });
      return;
    }
    this.current = call;
    this.events.onIncomingCall?.({ ...call });
    this.later(INBOUND_RING_TIMEOUT_MS, () => this.finish("missed", { error: "Not answered in time" }));
  }

  async answer(): Promise<void> {
    if (this.current?.state !== "incoming") throw new SipError("There is no incoming call to answer.");
    await ensureMicrophone().catch(() => undefined); // mock works without a microphone
    this.clearTimers();
    const call = this.update({ state: "answered", answeredAt: Date.now() });
    if (call) this.events.onCallAnswered?.(call);
  }

  async reject(): Promise<void> {
    if (this.current?.state !== "incoming") throw new SipError("There is no incoming call to reject.");
    this.finish("rejected", { statusCode: 603, error: "Rejected by agent" });
  }

  async hangup(): Promise<void> {
    const call = this.current;
    if (!call) return;
    if (call.state === "incoming") return this.reject();
    this.update({ state: "ending" });
    if (call.state === "answered") this.finish("completed");
    else this.finish("missed", { statusCode: 487, error: "Cancelled by agent before answer" });
  }

  mute(): void {
    this.emitUpdated({ muted: true });
  }

  unmute(): void {
    this.emitUpdated({ muted: false });
  }

  async hold(): Promise<void> {
    if (this.current?.state !== "answered") throw new SipError("Hold is only possible during an answered call.");
    this.emitUpdated({ held: true });
  }

  async resume(): Promise<void> {
    this.emitUpdated({ held: false });
  }

  sendDtmf(): void {
    /* nothing to send in mock mode */
  }
}

// ============================================================================ real (SIP.js)
function redact(text: string): string {
  return text.replace(/^((?:Proxy-)?Authorization:).*$/gim, "$1 [redacted]");
}

function userFromHeader(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const match = value.match(/(?:sips?|tel):([^@;>]+)/i);
  return (match ? match[1] : value).trim() || undefined;
}

export class RealSipClient extends BaseSipClient {
  readonly mode = "real" as const;
  readonly supportsHold = true;
  private ua: UserAgent | null = null;
  private registerer: Registerer | null = null;
  private session: Session | null = null;
  /** Set when we know why the session ended before SIP.js reports Terminated. */
  private pendingEnd: { reason: CallEndReason; error?: string; statusCode?: number } | null = null;
  /** True once the PBX sent 200 OK for our INVITE (used to diagnose media setup failures). */
  private remoteAccepted = false;
  /** Last SIP.js warning/error, appended to otherwise-unexplained failures. */
  private lastSipLog: string | null = null;

  constructor(
    private config: SipConfig,
    events: SipClientEvents,
  ) {
    super(events);
  }

  // ------------------------------------------------------------------ registration
  async connect(): Promise<void> {
    const problems = validateSipConfig(this.config);
    if (problems.length) {
      this.setRegistration("failed", `SIP configuration incomplete: ${problems.join("; ")}`);
      return;
    }
    await this.disconnect();
    this.setRegistration("connecting");

    const uri = UserAgent.makeURI(this.config.uri);
    if (!uri) {
      this.setRegistration("failed", `Invalid VITE_SIP_URI: ${this.config.uri}`);
      return;
    }
    const contact = this.config.contactUri ? UserAgent.makeURI(this.config.contactUri) : undefined;

    const ua = new UserAgent({
      uri,
      displayName: this.config.displayName,
      authorizationUsername: this.config.authorizationUsername,
      authorizationPassword: this.config.password,
      contactName: contact?.user,
      transportOptions: { server: this.config.wssUrl, connectionTimeout: 10 },
      sessionDescriptionHandlerFactoryOptions: {
        peerConnectionConfiguration: { iceServers: this.config.iceServers },
      },
      logBuiltinEnabled: false,
      logLevel: "warn",
      // Never print credentials / auth headers.
      logConnector: (level, category, _label, content) => {
        const line = `[sip.js ${category}] ${redact(content)}`;
        this.lastSipLog = redact(content).split("\n")[0].slice(0, 300);
        if (level === "error") console.error(line);
        else console.warn(line);
      },
      delegate: {
        onInvite: (invitation) => this.handleInvite(invitation),
        onDisconnect: (error) => {
          if (!error) return;
          if (this.current) this.terminateCurrent("failed", "Connection to the PBX was lost during the call.");
          this.setRegistration("failed", `Connection to the PBX lost (${error.message}). Check network/VPN and click Reconnect.`);
        },
      },
    });
    this.ua = ua;

    try {
      await ua.start();
    } catch (error) {
      this.ua = null;
      this.setRegistration(
        "failed",
        `Cannot open WebSocket to ${this.config.wssUrl} (${(error as Error).message}). ` +
          "Check that the PBX is reachable on this network, the port is open, and the TLS certificate is trusted " +
          `(open ${this.config.wssUrl.replace(/^wss:/, "https:").replace(/^ws:/, "http:")} in a browser tab and accept it).`,
      );
      return;
    }

    const registerer = new Registerer(ua, { expires: 300 });
    this.registerer = registerer;
    registerer.stateChange.addListener((state) => {
      if (state === RegistererState.Registered) this.setRegistration("registered");
      if (state === RegistererState.Unregistered && this.registration === "registered") this.setRegistration("unregistered");
    });

    let answered = false;
    const timeout = setTimeout(() => {
      if (!answered && this.registration === "connecting") {
        this.setRegistration("failed", "No answer to REGISTER from the PBX. Check the SIP domain and that the extension exists.");
      }
    }, REGISTRATION_TIMEOUT_MS);
    try {
      await registerer.register({
        requestDelegate: {
          onAccept: () => {
            answered = true;
          },
          onReject: (response: IncomingResponse) => {
            answered = true;
            const { statusCode, reasonPhrase } = response.message;
            const hint =
              statusCode === 401 || statusCode === 403 || statusCode === 407
                ? "wrong extension username/password or authorization username"
                : statusCode === 404
                  ? "extension not found on this SIP domain"
                  : "see PBX logs";
            this.setRegistration("failed", `Registration rejected: ${statusCode} ${reasonPhrase} (${hint}).`);
          },
        },
      });
    } catch (error) {
      this.setRegistration("failed", `Registration error: ${(error as Error).message}`);
    } finally {
      // The timeout only matters while waiting for the first response.
      if (answered) clearTimeout(timeout);
    }
  }

  async disconnect(): Promise<void> {
    if (this.current) await this.hangup().catch(() => undefined);
    try {
      if (this.registerer && this.registration === "registered") await this.registerer.unregister();
    } catch {
      /* ignore */
    }
    try {
      await this.ua?.stop();
    } catch {
      /* ignore */
    }
    this.ua = null;
    this.registerer = null;
    if (this.registration !== "disconnected") this.setRegistration("disconnected");
  }

  // ------------------------------------------------------------------ outbound
  async call(target: string, displayNumber?: string): Promise<SipCall> {
    this.assertCanCall();
    if (!this.ua) throw new SipError("Softphone is not connected.");
    const domain = this.config.domain || UserAgent.makeURI(this.config.uri)?.host;
    const uri = UserAgent.makeURI(`sip:${target}@${domain}`);
    if (!uri) throw new SipError(`Cannot build a SIP URI for "${target}".`);

    this.current = this.newCall({ direction: "outbound", remoteNumber: displayNumber || target, state: "connecting" });
    const snapshot = { ...this.current };
    try {
      await ensureMicrophone();
    } catch (error) {
      this.finish("failed", { error: (error as Error).message });
      throw error;
    }

    const inviter = new Inviter(this.ua, uri, {
      sessionDescriptionHandlerOptions: { constraints: { audio: true, video: false } },
      earlyMedia: true,
    });
    this.bindSession(inviter);
    this.update({ sipCallId: inviter.request.callId });

    try {
      await inviter.invite({
        requestDelegate: {
          onProgress: (response: IncomingResponse) => {
            const code = response.message.statusCode;
            if ((code === 180 || code === 183) && this.current?.state !== "ringing" && this.current?.state !== "answered") {
              const call = this.update({ state: "ringing" });
              if (call) this.events.onCallRinging?.(call);
            }
          },
          onAccept: () => {
            this.remoteAccepted = true;
          },
          onReject: (response: IncomingResponse) => {
            const statusCode = response.message.statusCode ?? 0;
            console.warn(`[softphone] INVITE rejected: ${statusCode} ${response.message.reasonPhrase}`);
            const { endReason, message } = describeSipStatus(statusCode, response.message.reasonPhrase);
            this.pendingEnd = { reason: endReason, error: message, statusCode };
          },
        },
      });
    } catch (error) {
      this.terminateCurrent("failed", `Could not start the call: ${(error as Error).message}`);
      throw new SipError(`Could not start the call: ${(error as Error).message}`);
    }

    const call = this.update({ state: this.current?.state === "connecting" ? "calling" : this.current?.state });
    if (call) this.events.onCallStarted?.(call);
    this.later(OUTBOUND_RING_TIMEOUT_MS, () => {
      if (this.current && this.current.state !== "answered") {
        this.pendingEnd = { reason: "missed", error: "No answer within 60 seconds", statusCode: 408 };
        void inviter.cancel().catch(() => this.finish("missed", { error: "No answer within 60 seconds" }));
      }
    });
    return snapshot;
  }

  // ------------------------------------------------------------------ inbound
  private handleInvite(invitation: Invitation): void {
    const request = invitation.request;
    const remoteNumber = invitation.remoteIdentity.uri.user || "unknown";
    let calledNumber: string | undefined;
    for (const header of CALLED_NUMBER_HEADERS) {
      const value = userFromHeader(request.getHeader(header));
      // Only phone-number-like values: the To header often carries our random WebRTC contact name.
      if (value && value !== this.config.username && /^\+?\d{3,15}$/.test(value)) {
        calledNumber = value;
        break;
      }
    }

    const call = this.newCall({
      direction: "inbound",
      remoteNumber,
      remoteDisplayName: invitation.remoteIdentity.displayName || undefined,
      calledNumber,
      sipCallId: request.callId,
      state: "incoming",
    });

    if (this.current) {
      void invitation.reject({ statusCode: 486 }).catch(() => undefined);
      this.events.onCallEnded?.({ ...call, state: "ended", endReason: "busy_rejected", endedAt: Date.now(), statusCode: 486, error: "Auto-rejected: agent already on a call" });
      return;
    }

    this.current = call;
    this.bindSession(invitation);
    invitation.delegate = {
      onCancel: () => {
        this.pendingEnd = { reason: "missed", error: "Caller hung up before answer" };
      },
    };
    this.events.onIncomingCall?.({ ...call });
    this.later(INBOUND_RING_TIMEOUT_MS, () => {
      if (this.current?.state === "incoming") {
        this.pendingEnd = { reason: "missed", error: "Not answered in time", statusCode: 480 };
        void invitation.reject({ statusCode: 480 }).catch(() => undefined);
      }
    });
  }

  async answer(): Promise<void> {
    const session = this.session;
    if (!(session instanceof Invitation) || this.current?.state !== "incoming") {
      throw new SipError("There is no incoming call to answer.");
    }
    try {
      await ensureMicrophone();
    } catch (error) {
      this.pendingEnd = { reason: "failed", error: (error as Error).message };
      await session.reject({ statusCode: 480 }).catch(() => undefined);
      throw error;
    }
    try {
      await session.accept({ sessionDescriptionHandlerOptions: { constraints: { audio: true, video: false } } });
    } catch (error) {
      this.terminateCurrent("failed", `Could not answer: ${(error as Error).message}`);
      throw new SipError(`Could not answer: ${(error as Error).message}`);
    }
  }

  async reject(): Promise<void> {
    const session = this.session;
    if (!(session instanceof Invitation) || this.current?.state !== "incoming") {
      throw new SipError("There is no incoming call to reject.");
    }
    this.pendingEnd = { reason: "rejected", error: "Rejected by agent", statusCode: 603 };
    await session.reject({ statusCode: 603 });
  }

  async hangup(): Promise<void> {
    const session = this.session;
    if (!session || !this.current) return;
    const wasAnswered = this.current.state === "answered";
    this.update({ state: "ending" });
    try {
      if (session.state === SessionState.Established) {
        await session.bye();
      } else if (session instanceof Inviter) {
        this.pendingEnd = { reason: "missed", error: "Cancelled by agent before answer", statusCode: 487 };
        await session.cancel();
      } else if (session instanceof Invitation) {
        this.pendingEnd = { reason: "rejected", error: "Rejected by agent", statusCode: 603 };
        await session.reject({ statusCode: 603 });
      }
    } catch (error) {
      this.terminateCurrent(wasAnswered ? "completed" : "failed", (error as Error).message);
    }
  }

  // ------------------------------------------------------------------ in-call controls
  private sdh(): Web.SessionDescriptionHandler | undefined {
    return this.session?.sessionDescriptionHandler as Web.SessionDescriptionHandler | undefined;
  }

  private applySenderTracks(): void {
    const call = this.current;
    this.sdh()?.enableSenderTracks(Boolean(call && !call.muted && !call.held));
  }

  mute(): void {
    this.update({ muted: true });
    this.applySenderTracks();
    this.emitUpdated({});
  }

  unmute(): void {
    this.update({ muted: false });
    this.applySenderTracks();
    this.emitUpdated({});
  }

  private async setHold(hold: boolean): Promise<void> {
    const session = this.session;
    if (!session || session.state !== SessionState.Established) throw new SipError("Hold needs an answered call.");
    const previous = session.sessionDescriptionHandlerOptionsReInvite;
    session.sessionDescriptionHandlerOptionsReInvite = { ...previous, hold } as typeof previous;
    await new Promise<void>((resolve, reject) => {
      session
        .invite({
          requestDelegate: {
            onAccept: () => {
              this.update({ held: hold });
              this.applySenderTracks();
              this.emitUpdated({});
              resolve();
            },
            onReject: (response: IncomingResponse) => {
              session.sessionDescriptionHandlerOptionsReInvite = previous;
              reject(new SipError(`PBX refused ${hold ? "hold" : "resume"} (${response.message.statusCode})`));
            },
          },
        })
        .catch((error: Error) => reject(new SipError(`Hold failed: ${error.message}`)));
    });
  }

  hold(): Promise<void> {
    return this.setHold(true);
  }

  resume(): Promise<void> {
    return this.setHold(false);
  }

  sendDtmf(digit: string): void {
    const sdh = this.sdh();
    if (this.session?.state !== SessionState.Established) return;
    if (sdh && sdh.sendDtmf(digit)) return;
    // Fallback: SIP INFO
    void this.session
      .info({
        requestOptions: {
          body: { contentDisposition: "render", contentType: "application/dtmf-relay", content: `Signal=${digit}\r\nDuration=160` },
        },
      })
      .catch(() => undefined);
  }

  /** Call again after a user gesture if the browser blocked autoplay. */
  async playRemoteAudio(): Promise<void> {
    await this.remoteAudio?.play();
  }

  // ------------------------------------------------------------------ session plumbing
  private bindSession(session: Session): void {
    this.session = session;
    this.pendingEnd = null;
    this.remoteAccepted = false;
    this.lastSipLog = null;
    session.stateChange.addListener((state) => {
      if (this.session !== session) return;
      if (state === SessionState.Established) this.onEstablished(session);
      if (state === SessionState.Terminated) this.onTerminated();
    });
  }

  private onEstablished(session: Session): void {
    this.clearTimers();
    const call = this.update({ state: "answered", answeredAt: Date.now() });
    const sdh = session.sessionDescriptionHandler as Web.SessionDescriptionHandler | undefined;
    if (sdh && this.remoteAudio) {
      this.remoteAudio.srcObject = sdh.remoteMediaStream;
      this.remoteAudio.play().catch(() => {
        this.emitUpdated({ error: "Browser blocked audio playback - click 'Enable audio'." });
      });
    }
    sdh?.peerConnection?.addEventListener("connectionstatechange", () => {
      if (sdh.peerConnection?.connectionState === "failed" && this.session === session) {
        this.pendingEnd = {
          reason: "failed",
          error: "Media connection failed (ICE). Check RTP ports on FreePBX, NAT and STUN/TURN settings.",
        };
        void session.bye().catch(() => this.onTerminated());
      }
    });
    if (call) this.events.onCallAnswered?.(call);
  }

  private onTerminated(): void {
    const call = this.current;
    if (!call) return;
    const pending = this.pendingEnd;
    this.pendingEnd = null;
    this.session = null;
    if (pending) this.finish(pending.reason, pending);
    else if (call.answeredAt) this.finish("completed");
    else if (this.remoteAccepted) {
      // 200 OK arrived but the WebRTC session could not be set up (SDP/DTLS/ICE).
      this.finish("failed", {
        error:
          "PBX answered but WebRTC media setup failed. On the extension enable: Media Encryption = DTLS-SRTP, " +
          "Enable DTLS = Yes, AVPF = Yes, ICE = Yes, rtcp-mux = Yes, codec Opus/ulaw." +
          (this.lastSipLog ? ` Details: ${this.lastSipLog}` : ""),
      });
    } else {
      const detail = this.lastSipLog ? ` Details: ${this.lastSipLog}` : " See the browser console ([sip.js] lines).";
      this.finish(call.direction === "inbound" ? "missed" : "failed", { error: `Call ended before it was answered.${detail}` });
    }
  }

  private terminateCurrent(reason: CallEndReason, error: string): void {
    this.session = null;
    this.pendingEnd = null;
    this.finish(reason, { error });
  }
}

// ============================================================================ factory
export function createSipClient(config: SipConfig, events: SipClientEvents): SipClient {
  return config.mode === "real" ? new RealSipClient(config, events) : new MockSipClient(events);
}
