// Forwards the softphone's own console lines ("[softphone] ...", "[sip.js ...]") to the
// backend (backend/client.log), so PBX issues can be checked without the browser console.
// Only those prefixes are sent; SIP auth headers are already redacted by SipClient.

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const PREFIXES = ["[softphone]", "[sip.js"];

type Line = { level: string; text: string; at: string };
let queue: Line[] = [];
let timer: number | undefined;

function stringify(arg: unknown): string {
  if (typeof arg === "string") return arg;
  try {
    return JSON.stringify(arg);
  } catch {
    return String(arg);
  }
}

function flush(): void {
  timer = undefined;
  if (!queue.length) return;
  const lines = queue.splice(0, 200);
  void fetch(`${BASE}/api/client-logs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
    keepalive: true,
  }).catch(() => undefined);
}

export function installRemoteConsole(): void {
  for (const level of ["info", "warn", "error"] as const) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      original(...args);
      if (typeof args[0] !== "string" || !PREFIXES.some((p) => (args[0] as string).startsWith(p))) return;
      queue.push({ level, text: args.map(stringify).join(" "), at: new Date().toISOString() });
      timer ??= window.setTimeout(flush, 1000);
    };
  }
}
