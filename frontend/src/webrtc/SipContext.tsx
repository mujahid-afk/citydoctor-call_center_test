// React bridge for SipClient. Components use `useSip()` and never import SIP.js.
//
// CRM concerns (logging calls to FastAPI) are NOT handled here: the provider
// forwards call events to the optional `onCallEvent` prop.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getSipConfig, normalizeDialNumber, publicSipSummary } from "./config";
import { MockSipClient, RealSipClient, createSipClient, type SimulatedInvite } from "./SipClient";
import { startTone, stopTone, unlockTones } from "./tones";
import type { RegistrationState, SipCall, SipClient, SipConfig, SipMode } from "./types";

export type SipCallEventType = "incoming" | "started" | "ringing" | "answered" | "updated" | "ended" | "failed";

export interface OutboundMeta {
  brandId?: number | null;
  purpose?: string | null;
  customerName?: string | null;
}

export interface SipCallEvent {
  type: SipCallEventType;
  call: SipCall;
  /** Extra CRM info supplied when dialing (outbound only). */
  meta?: OutboundMeta;
}

interface SipContextValue {
  mode: SipMode | null;
  configSummary: ReturnType<typeof publicSipSummary> | null;
  extension: string;
  registration: RegistrationState;
  registrationError: string | null;
  call: SipCall | null;
  /** The call that just ended (for wrap-up), until dismissed. */
  lastEndedCall: SipCall | null;
  actionError: string | null;
  supportsHold: boolean;
  /** False until the agent clicks the page: browsers keep a page silent until then (no ringtone). */
  soundOn: boolean;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  dial(number: string, meta?: OutboundMeta): Promise<void>;
  answer(): Promise<void>;
  reject(): Promise<void>;
  hangup(): Promise<void>;
  toggleMute(): void;
  toggleHold(): Promise<void>;
  sendDtmf(digit: string): void;
  /** Blind transfer of the answered call to an extension or number. */
  transfer(target: string): Promise<void>;
  simulateIncomingCall(from: string, invite?: SimulatedInvite): void;
  enableAudio(): Promise<void>;
  dismissLastCall(): void;
  clearActionError(): void;
  normalize(number: string): string;
}

const SipContext = createContext<SipContextValue | null>(null);

export function SipProvider({
  children,
  onCallEvent,
}: {
  children: ReactNode;
  onCallEvent?: (event: SipCallEvent) => void;
}) {
  const [config, setConfig] = useState<SipConfig | null>(null);
  const [registration, setRegistration] = useState<RegistrationState>("disconnected");
  const [registrationError, setRegistrationError] = useState<string | null>(null);
  const [call, setCall] = useState<SipCall | null>(null);
  const [lastEndedCall, setLastEndedCall] = useState<SipCall | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(false);

  const clientRef = useRef<SipClient | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const metaRef = useRef<OutboundMeta | undefined>(undefined);
  const onEventRef = useRef(onCallEvent);
  onEventRef.current = onCallEvent;

  const emit = useCallback((type: SipCallEventType, sipCall: SipCall) => {
    onEventRef.current?.({ type, call: sipCall, meta: sipCall.direction === "outbound" ? metaRef.current : undefined });
  }, []);

  // Create the client once and register.
  useEffect(() => {
    let cancelled = false;
    let client: SipClient | null = null;
    void getSipConfig().then((cfg) => {
      if (cancelled) return;
      setConfig(cfg);
      client = createSipClient(cfg, {
        onRegistrationStateChanged: (state, error) => {
          setRegistration(state);
          setRegistrationError(state === "failed" ? (error ?? "Registration failed") : null);
        },
        onIncomingCall: (c) => {
          setLastEndedCall(null);
          setCall(c);
          emit("incoming", c);
        },
        onCallStarted: (c) => {
          setCall(c);
          emit("started", c);
        },
        onCallRinging: (c) => {
          setCall(c);
          emit("ringing", c);
        },
        onCallAnswered: (c) => {
          setCall(c);
          emit("answered", c);
        },
        onCallUpdated: (c) => {
          setCall(c);
          emit("updated", c);
        },
        onCallEnded: (c) => {
          // A busy auto-reject concerns a *second* call; keep the active one on screen.
          if (c.endReason !== "busy_rejected") {
            setCall(null);
            setLastEndedCall(c);
          } else {
            setActionError(`Incoming call from ${c.remoteNumber} was auto-rejected because you are on a call.`);
          }
          emit("ended", c);
        },
        onCallFailed: (c, error) => {
          setCall(null);
          setLastEndedCall(c);
          setActionError(error);
          emit("failed", c);
        },
      });
      client.attachRemoteAudio(audioRef.current);
      clientRef.current = client;
      void client.connect();
    });
    return () => {
      cancelled = true;
      void client?.disconnect();
      clientRef.current = null;
    };
  }, [emit]);

  // Call tones: local ringback for outbound ringing (unless the PBX sends early
  // media), ringtone for incoming calls.
  const tone =
    call?.direction === "outbound" && (call.state === "calling" || call.state === "ringing") && !call.earlyMedia
      ? "ringback"
      : call?.direction === "inbound" && call.state === "incoming"
        ? "ringtone"
        : null;
  useEffect(() => {
    if (tone) startTone(tone);
    else stopTone();
  }, [tone]);
  useEffect(() => stopTone, []);

  // Browser notification for an incoming call while the CRM tab is in the background.
  const incomingId = call?.direction === "inbound" && call.state === "incoming" ? call.id : null;
  useEffect(() => {
    if (!incomingId || !call || document.visibilityState === "visible") return;
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const notification = new Notification("Incoming call", {
      body: call.remoteDisplayName ? `${call.remoteDisplayName} (${call.remoteNumber})` : call.remoteNumber,
      tag: incomingId,
      requireInteraction: true,
    });
    notification.onclick = () => {
      window.focus();
      notification.close();
    };
    return () => notification.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingId]);

  // Browsers only allow audio and permission prompts after a user gesture: unlock
  // tones on clicks / key presses until it works, and ask for notification permission once.
  useEffect(() => {
    let askedNotifications = false;
    const onGesture = () => {
      void unlockTones().then((on) => {
        setSoundOn(on);
        if (on) {
          document.removeEventListener("pointerdown", onGesture);
          document.removeEventListener("keydown", onGesture);
        }
      });
      if (!askedNotifications && "Notification" in window && Notification.permission === "default") {
        askedNotifications = true;
        void Notification.requestPermission();
      }
    };
    document.addEventListener("pointerdown", onGesture);
    document.addEventListener("keydown", onGesture);
    return () => {
      document.removeEventListener("pointerdown", onGesture);
      document.removeEventListener("keydown", onGesture);
    };
  }, []);

  const run = useCallback(async (action: (client: SipClient) => Promise<void> | void) => {
    const client = clientRef.current;
    if (!client) return;
    setActionError(null);
    try {
      await action(client);
    } catch (error) {
      setActionError((error as Error).message);
    }
  }, []);

  const normalize = useCallback((number: string) => (config ? normalizeDialNumber(number, config) : number.trim()), [config]);

  const value = useMemo<SipContextValue>(
    () => ({
      mode: config?.mode ?? null,
      configSummary: config ? publicSipSummary(config) : null,
      extension: config?.mode === "mock" ? config.username || "9001" : config?.username ?? "",
      registration,
      registrationError,
      call,
      lastEndedCall,
      actionError,
      supportsHold: clientRef.current?.supportsHold ?? false,
      soundOn,
      connect: () => run((c) => c.connect()),
      disconnect: () => run((c) => c.disconnect()),
      dial: (number, meta) =>
        run(async (c) => {
          const target = normalize(number);
          if (!target) throw new Error("Enter a phone number to call.");
          metaRef.current = meta;
          setLastEndedCall(null);
          const started = await c.call(target, number.trim());
          setCall(started);
        }),
      answer: () => run((c) => c.answer()),
      reject: () => run((c) => c.reject()),
      hangup: () => run((c) => c.hangup()),
      toggleMute: () => void run((c) => (call?.muted ? c.unmute() : c.mute())),
      toggleHold: () => run((c) => (call?.held ? c.resume() : c.hold())),
      sendDtmf: (digit) => clientRef.current?.sendDtmf(digit),
      transfer: (target) =>
        run(async (c) => {
          const normalized = normalize(target);
          if (!normalized) throw new Error("Enter an extension or number to transfer to.");
          await c.transfer(normalized);
        }),
      simulateIncomingCall: (from, invite) =>
        void run((c) => {
          if (!(c instanceof MockSipClient)) throw new Error("Simulated calls are only available in mock mode.");
          setLastEndedCall(null);
          c.simulateIncomingCall(from, invite);
        }),
      enableAudio: () =>
        run(async (c) => {
          if (c instanceof RealSipClient) await c.playRemoteAudio();
          setCall((current) => (current ? { ...current, error: undefined } : current));
        }),
      dismissLastCall: () => setLastEndedCall(null),
      clearActionError: () => setActionError(null),
      normalize,
    }),
    [config, registration, registrationError, call, lastEndedCall, actionError, soundOn, run, normalize],
  );

  return (
    <SipContext.Provider value={value}>
      {children}
      {/* Remote party audio (real mode). */}
      <audio ref={audioRef} autoPlay playsInline className="hidden" />
    </SipContext.Provider>
  );
}

export function useSip(): SipContextValue {
  const value = useContext(SipContext);
  if (!value) throw new Error("useSip must be used inside <SipProvider>");
  return value;
}
