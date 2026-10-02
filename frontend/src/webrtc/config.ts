// The ONLY module that knows where SIP settings come from.
//
// MVP: settings are read from Vite env variables (frontend/.env). Anything in a
// VITE_* variable ends up in the JavaScript bundle, so this is for development
// only. For production, replace `getSipConfig()` with a call to a backend
// endpoint that returns short-lived, per-user SIP credentials - nothing else in
// the app needs to change.

import type { DialFormat, SipConfig, SipMode } from "./types";

const env = import.meta.env;

function str(value: string | undefined): string {
  return (value ?? "").trim();
}

function iceServers(): RTCIceServer[] {
  const servers: RTCIceServer[] = [];
  const stun = str(env.VITE_STUN_URL);
  if (stun) servers.push({ urls: stun.split(",").map((s) => s.trim()) });
  const turn = str(env.VITE_TURN_URL);
  if (turn) {
    servers.push({
      urls: turn.split(",").map((s) => s.trim()),
      username: str(env.VITE_TURN_USERNAME) || undefined,
      credential: str(env.VITE_TURN_PASSWORD) || undefined,
    });
  }
  return servers;
}

export async function getSipConfig(): Promise<SipConfig> {
  const mode: SipMode = str(env.VITE_SIP_MODE).toLowerCase() === "real" ? "real" : "mock";
  const domain = str(env.VITE_SIP_DOMAIN);
  const username = str(env.VITE_SIP_USERNAME);
  const uri = str(env.VITE_SIP_URI) || (username && domain ? `sip:${username}@${domain}` : "");
  const format = str(env.VITE_SIP_DIAL_FORMAT).toLowerCase() as DialFormat;
  return {
    mode,
    wssUrl: str(env.VITE_SIP_WSS_URL),
    domain,
    uri,
    username,
    password: env.VITE_SIP_PASSWORD ?? "",
    authorizationUsername: str(env.VITE_SIP_AUTHORIZATION_USERNAME) || username,
    displayName: str(env.VITE_SIP_DISPLAY_NAME) || "Voice CRM",
    contactUri: str(env.VITE_SIP_CONTACT_URI),
    iceServers: iceServers(),
    dialFormat: (["raw", "e164", "e164_no_plus", "national"] as const).includes(format) ? format : "raw",
    dialPrefix: str(env.VITE_SIP_DIAL_PREFIX),
    defaultCountryCode: str(env.VITE_DEFAULT_COUNTRY_CODE).replace(/\D/g, "") || "971",
  };
}

/** Human-readable list of problems with a real-mode config (empty = OK). */
export function validateSipConfig(config: SipConfig): string[] {
  if (config.mode !== "real") return [];
  const problems: string[] = [];
  if (!config.wssUrl) problems.push("VITE_SIP_WSS_URL is not set (e.g. wss://192.168.1.222:8089/ws)");
  else if (!/^wss?:\/\//i.test(config.wssUrl)) problems.push("VITE_SIP_WSS_URL must start with wss:// (or ws://)");
  if (!config.domain && !config.uri) problems.push("VITE_SIP_DOMAIN or VITE_SIP_URI is not set");
  if (!config.uri) problems.push("VITE_SIP_URI could not be built (set VITE_SIP_URI or VITE_SIP_USERNAME + VITE_SIP_DOMAIN)");
  if (!config.username && !config.authorizationUsername) problems.push("VITE_SIP_USERNAME is not set");
  if (!config.password) problems.push("VITE_SIP_PASSWORD is not set");
  return problems;
}

/** Safe-to-display summary (never includes the password). */
export function publicSipSummary(config: SipConfig) {
  return {
    mode: config.mode,
    wssUrl: config.wssUrl || "—",
    uri: config.uri || "—",
    extension: config.username || "—",
    domain: config.domain || "—",
    dialFormat: config.dialFormat + (config.dialPrefix ? ` (prefix ${config.dialPrefix})` : ""),
    iceServers: config.iceServers.length ? config.iceServers.map((s) => s.urls).flat().join(", ") : "none (LAN)",
    passwordConfigured: Boolean(config.password),
  };
}

/**
 * Convert what the agent typed into what FreePBX expects. The required format
 * depends on the PBX outbound routes, so it is configured, not assumed:
 *
 *   VITE_SIP_DIAL_FORMAT=raw          -> digits as typed ("+" kept)       +971501234567
 *   VITE_SIP_DIAL_FORMAT=e164         -> +<country><number>               +971501234567
 *   VITE_SIP_DIAL_FORMAT=e164_no_plus -> <country><number>                971501234567
 *   VITE_SIP_DIAL_FORMAT=national     -> 0<number>                        0501234567
 *   VITE_SIP_DIAL_PREFIX=9            -> prepended after formatting       9+971...
 *
 * Short numbers (internal extensions, <= 6 digits) are always dialed as typed.
 */
export function normalizeDialNumber(input: string, config: Pick<SipConfig, "dialFormat" | "dialPrefix" | "defaultCountryCode">): string {
  const trimmed = input.trim();
  const hasPlus = trimmed.startsWith("+") || trimmed.startsWith("00");
  let digits = trimmed.replace(/[^\d*#]/g, "");
  if (trimmed.startsWith("00")) digits = digits.slice(2);
  if (!digits) return "";
  if (digits.length <= 6 || /[*#]/.test(digits)) return digits;

  const cc = config.defaultCountryCode;
  // National significant number (without country code / trunk prefix).
  let nsn: string;
  if (hasPlus || digits.startsWith(cc)) nsn = digits.startsWith(cc) ? digits.slice(cc.length) : digits;
  else nsn = digits.replace(/^0/, "");

  let result: string;
  switch (config.dialFormat) {
    case "e164":
      result = hasPlus && !digits.startsWith(cc) ? `+${digits}` : `+${cc}${nsn}`;
      break;
    case "e164_no_plus":
      result = hasPlus && !digits.startsWith(cc) ? digits : `${cc}${nsn}`;
      break;
    case "national":
      result = hasPlus && !digits.startsWith(cc) ? `00${digits}` : `0${nsn}`;
      break;
    default:
      result = hasPlus ? `+${digits}` : digits;
  }
  return `${config.dialPrefix}${result}`;
}

/** Headers FreePBX/Asterisk commonly use to tell an extension which DID was called. */
export const CALLED_NUMBER_HEADERS = ["X-Called-Number", "X-DID", "P-Called-Party-ID", "Diversion", "To"];
