import { Mic, Settings } from "lucide-react";
import { useRef, useState } from "react";
import { ensureMicrophone } from "../webrtc/SipClient";
import { useSip } from "../webrtc/SipContext";
import { Card, CardHeader, btnSecondary } from "./ui";

/** Read-only SIP configuration (never shows the password) + microphone test. */
export function SettingsPanel({ backendOk }: { backendOk: boolean | null }) {
  const sip = useSip();
  const summary = sip.configSummary;
  const [level, setLevel] = useState<number | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const running = useRef(false);

  const testMic = async () => {
    if (running.current) return;
    setMicError(null);
    try {
      await ensureMicrophone();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      running.current = true;
      const started = Date.now();
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        const peak = data.reduce((max, v) => Math.max(max, Math.abs(v - 128)), 0) / 128;
        setLevel(peak);
        if (Date.now() - started < 6000) requestAnimationFrame(tick);
        else {
          stream.getTracks().forEach((t) => t.stop());
          void ctx.close();
          running.current = false;
          setLevel(null);
        }
      };
      tick();
    } catch (e) {
      setMicError((e as Error).message);
    }
  };

  const rows: Array<[string, string]> = summary
    ? [
        ["SIP mode", summary.mode === "real" ? "Real (SIP.js / WebRTC)" : "Mock (no PBX connection)"],
        ["WSS URL", summary.wssUrl],
        ["SIP URI", summary.uri],
        ["Extension", summary.extension],
        ["SIP domain", summary.domain],
        ["Password", summary.passwordConfigured ? "configured (hidden)" : "not set"],
        ["Dial format", summary.dialFormat],
        ["STUN / TURN", summary.iceServers],
        ["Registration", sip.registration],
        ["CRM backend", backendOk === null ? "checking…" : backendOk ? "reachable" : "unreachable"],
      ]
    : [];

  return (
    <Card id="settings">
      <CardHeader icon={<Settings className="h-4 w-4" />} title="Settings" subtitle="Configured in frontend/.env - restart `npm run dev` after changes" />
      <div className="grid gap-6 p-5 lg:grid-cols-2">
        <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-500">{k}</dt>
              <dd className="break-all font-mono text-xs leading-5 text-slate-800">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="space-y-3">
          <p className="text-sm font-medium text-slate-700">Microphone test</p>
          <button type="button" className={btnSecondary} onClick={() => void testMic()}>
            <Mic className="h-4 w-4" /> Test microphone
          </button>
          {level !== null && (
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-75" style={{ width: `${Math.min(100, level * 250)}%` }} />
            </div>
          )}
          {level !== null && <p className="text-xs text-slate-500">Speak now - the bar should move.</p>}
          {micError && <p className="text-sm text-red-600">{micError}</p>}
          <p className="text-xs leading-relaxed text-slate-500">
            Voice goes directly from this browser to FreePBX over WSS/WebRTC. The CRM backend only stores call records.
          </p>
        </div>
      </div>
    </Card>
  );
}
