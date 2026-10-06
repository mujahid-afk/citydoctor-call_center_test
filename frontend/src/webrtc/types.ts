// SIP/WebRTC types. Nothing in here knows about the CRM.

export type SipMode = "mock" | "real";

export type RegistrationState = "disconnected" | "connecting" | "registered" | "unregistered" | "failed";

/** Finite call state for the single active call. */
export type CallState =
  | "idle"
  | "connecting" // outbound: preparing media / sending INVITE
  | "incoming" // inbound: INVITE received, waiting for answer/reject
  | "calling" // outbound: INVITE sent (100 Trying)
  | "ringing" // outbound: 180/183 received
  | "answered" // media established (on call)
  | "ending" // BYE/CANCEL in progress
  | "ended"
  | "failed";

export type CallDirection = "inbound" | "outbound";

/** Why a call finished; mapped to CRM statuses by the call logger. */
export type CallEndReason =
  | "completed" // answered and then hung up (either side)
  | "rejected" // declined by us (inbound) or by the callee (486/603)
  | "missed" // never answered (caller cancelled, no answer, timeout)
  | "busy_rejected" // inbound auto-rejected because we were already on a call
  | "failed"; // network / PBX / media error

export interface SipCall {
  /** Local ID for this call (stable across events). */
  id: string;
  direction: CallDirection;
  /** Customer number (caller for inbound, dialed number for outbound). */
  remoteNumber: string;
  remoteDisplayName?: string;
  /** Inbound only: the DID that was called, if the PBX passes it (used to match the brand). */
  calledNumber?: string;
  /** Inbound only: routing labels the PBX dialplan adds to the INVITE (X-Brand, X-Queue, X-IVR-Path). */
  brandLabel?: string;
  queueName?: string;
  ivrPath?: string;
  /** Inbound only: when the caller entered the queue (X-Queue-Start, epoch ms); used for the wait time. */
  queueEnteredAt?: number;
  /** SIP Call-ID header. */
  sipCallId?: string;
  state: CallState;
  muted: boolean;
  held: boolean;
  startedAt: number;
  answeredAt?: number;
  endedAt?: number;
  endReason?: CallEndReason;
  /** SIP status code that ended the call, if any. */
  statusCode?: number;
  error?: string;
}

export interface SipClientEvents {
  onRegistrationStateChanged?(state: RegistrationState, error?: string): void;
  onRegistered?(): void;
  onRegistrationFailed?(error: string): void;
  onIncomingCall?(call: SipCall): void;
  /** Outbound INVITE sent. */
  onCallStarted?(call: SipCall): void;
  onCallRinging?(call: SipCall): void;
  onCallAnswered?(call: SipCall): void;
  /** Mute / hold changes. */
  onCallUpdated?(call: SipCall): void;
  /** Final event for calls that ended normally (completed, rejected, missed, busy_rejected). */
  onCallEnded?(call: SipCall): void;
  /** Final event for calls that failed. */
  onCallFailed?(call: SipCall, error: string): void;
}

export interface SipClient {
  readonly mode: SipMode;
  readonly supportsHold: boolean;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  /** Place a call; ``target`` is already normalized for the PBX dial plan. */
  call(target: string, displayNumber?: string): Promise<SipCall>;
  answer(): Promise<void>;
  reject(): Promise<void>;
  hangup(): Promise<void>;
  mute(): void;
  unmute(): void;
  hold(): Promise<void>;
  resume(): Promise<void>;
  sendDtmf(digit: string): void;
  /** Element used for remote audio playback (real mode). */
  attachRemoteAudio(element: HTMLAudioElement | null): void;
}

export interface SipConfig {
  mode: SipMode;
  wssUrl: string;
  domain: string;
  uri: string;
  username: string;
  password: string;
  authorizationUsername: string;
  displayName: string;
  contactUri: string;
  iceServers: RTCIceServer[];
  dialFormat: DialFormat;
  dialPrefix: string;
  defaultCountryCode: string;
}

export type DialFormat = "raw" | "e164" | "e164_no_plus" | "national";
