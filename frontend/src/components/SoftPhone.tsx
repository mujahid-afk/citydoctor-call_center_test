import { Delete, Mic, MicOff, Pause, Phone, PhoneForwarded, PhoneIncoming, PhoneOff, Play, RefreshCw, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { PURPOSES, type Brand } from "../api";
import { formatDuration } from "../lib/format";
import { useNow } from "../lib/useNow";
import { useSip } from "../webrtc/SipContext";
import type { CallState, RegistrationState } from "../webrtc/types";
import { DialPad } from "./DialPad";
import { Spinner, btnSecondary, inputClass, labelClass } from "./ui";

const REG_STYLE: Record<RegistrationState, { label: string; dot: string; text: string }> = {
  registered: { label: "Registered", dot: "bg-emerald-500", text: "text-emerald-700" },
  connecting: { label: "Connecting", dot: "bg-amber-400 animate-pulse", text: "text-amber-700" },
  disconnected: { label: "Disconnected", dot: "bg-slate-400", text: "text-slate-600" },
  unregistered: { label: "Unregistered", dot: "bg-slate-400", text: "text-slate-600" },
  failed: { label: "Registration failed", dot: "bg-red-500", text: "text-red-700" },
};

const CALL_LABEL: Record<CallState, string> = {
  idle: "Idle",
  connecting: "Connecting",
  incoming: "Incoming",
  calling: "Calling",
  ringing: "Ringing",
  answered: "On Call",
  ending: "Ending",
  ended: "Ended",
  failed: "Failed",
};

export function SoftPhone({
  brands,
  number,
  onNumberChange,
  onSimulateIncoming,
  simulating,
}: {
  brands: Brand[];
  number: string;
  onNumberChange: (value: string) => void;
  onSimulateIncoming: () => void;
  simulating: boolean;
}) {
  const sip = useSip();
  const { call, registration } = sip;
  const [brandId, setBrandId] = useState<number | "">("");
  const [purpose, setPurpose] = useState<string>("Follow Up");
  const [transferTo, setTransferTo] = useState("");
  const now = useNow(call?.state === "answered");

  useEffect(() => {
    if (brandId === "" && brands.length) setBrandId(brands[0].id);
  }, [brands, brandId]);

  const state: CallState = call?.state ?? (sip.lastEndedCall ? sip.lastEndedCall.state : "idle");
  const onCall = call?.state === "answered";
  const busy = Boolean(call);
  const registered = registration === "registered";
  const reg = REG_STYLE[registration];
  const timer = call?.answeredAt ? formatDuration(Math.max(0, Math.floor((now - call.answeredAt) / 1000))) : "00:00";
  const preview = number.trim() ? sip.normalize(number) : "";

  const press = (key: string) => {
    if (onCall) sip.sendDtmf(key);
    else if (!busy) onNumberChange(number + key);
  };

  const dial = () => {
    const brand = brands.find((b) => b.id === brandId);
    void sip.dial(number, { brandId: brand?.id ?? null, purpose });
  };

  return (
    <section id="softphone" className="scroll-mt-20 rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
            <Phone className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-900">Voice Phone</h2>
            <p className="text-xs text-slate-500">
              Ext. {sip.extension || "—"} · {sip.mode === "real" ? "WebRTC" : "Mock mode"}
            </p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${reg.text}`}>
          <span className={`h-2 w-2 rounded-full ${reg.dot}`} />
          {reg.label}
        </span>
      </div>

      <div className="space-y-4 p-5">
        {registration === "failed" && sip.registrationError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <p className="font-medium">Cannot register with the PBX</p>
            <p className="mt-1 break-words">{sip.registrationError}</p>
          </div>
        )}
        {registered && !sip.soundOn && (
          // Any click on the page turns sound on (see SipContext); this button just asks for one.
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-left text-xs text-amber-800 hover:bg-amber-100"
          >
            <Volume2 className="h-4 w-4 shrink-0" />
            <span>
              <span className="font-medium">Sound is off - click to turn on the ringtone.</span> The browser keeps the page
              silent until you click it.
            </span>
          </button>
        )}
        {(registration === "failed" || registration === "disconnected" || registration === "unregistered") && (
          <button type="button" className={`${btnSecondary} w-full`} onClick={() => void sip.connect()}>
            <RefreshCw className="h-4 w-4" /> Reconnect
          </button>
        )}

        {/* Call state + timer */}
        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
          <span className="text-xs text-slate-500">
            Call: <span className="font-semibold text-slate-800">{CALL_LABEL[state]}</span>
            {call?.held && <span className="ml-1 text-amber-600">(on hold)</span>}
            {call?.muted && <span className="ml-1 text-amber-600">(muted)</span>}
          </span>
          <span className="font-mono text-sm tabular-nums text-slate-700">{timer}</span>
        </div>

        {busy ? (
          <div className="text-center">
            <p className="text-xs uppercase tracking-wide text-slate-400">
              {call!.direction === "inbound" ? "Incoming from" : "Calling"}
            </p>
            <p className="mt-1 text-2xl font-semibold tracking-wide text-slate-900">{call!.remoteNumber}</p>
            {call!.remoteDisplayName && <p className="text-sm text-slate-500">{call!.remoteDisplayName}</p>}
          </div>
        ) : (
          <div>
            <div className="relative">
              <input
                value={number}
                onChange={(e) => onNumberChange(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && registered && dial()}
                placeholder="+971 50 123 4567"
                className={`${inputClass} pr-10 text-center text-xl font-semibold tracking-wide`}
                aria-label="Phone number"
              />
              {number && (
                <button
                  type="button"
                  onClick={() => onNumberChange(number.slice(0, -1))}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700"
                  aria-label="Delete digit"
                >
                  <Delete className="h-5 w-5" />
                </button>
              )}
            </div>
            {preview && preview !== number.trim() && (
              <p className="mt-1 text-center text-[11px] text-slate-400">Dials as {preview}</p>
            )}
          </div>
        )}

        <DialPad onPress={press} disabled={busy && !onCall} />

        {!busy && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelClass}>Brand</label>
              <select className={inputClass} value={brandId} onChange={(e) => setBrandId(Number(e.target.value))}>
                {brands.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>Purpose</label>
              <select className={inputClass} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                {PURPOSES.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Primary actions */}
        {call?.state === "incoming" ? (
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={() => void sip.answer()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-700">
              <Phone className="h-5 w-5" /> Answer
            </button>
            <button type="button" onClick={() => void sip.reject()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 py-3 font-semibold text-white hover:bg-red-700">
              <PhoneOff className="h-5 w-5" /> Reject
            </button>
          </div>
        ) : busy ? (
          <div className="grid grid-cols-3 gap-2">
            <button type="button" disabled={!onCall} onClick={sip.toggleMute} className={btnSecondary}>
              {call!.muted ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
              {call!.muted ? "Unmute" : "Mute"}
            </button>
            <button type="button" disabled={!onCall || !sip.supportsHold} onClick={() => void sip.toggleHold()} className={btnSecondary}>
              {call!.held ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
              {call!.held ? "Resume" : "Hold"}
            </button>
            <button type="button" onClick={() => void sip.hangup()} className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700">
              <PhoneOff className="h-4 w-4" /> Hang Up
            </button>
            {onCall && (
              <form
                className="col-span-3 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (transferTo.trim()) void sip.transfer(transferTo).then(() => setTransferTo(""));
                }}
              >
                <input
                  value={transferTo}
                  onChange={(e) => setTransferTo(e.target.value)}
                  placeholder="Transfer to ext. or number"
                  className={`${inputClass} min-w-0 flex-1`}
                  aria-label="Transfer to"
                />
                <button type="submit" disabled={!transferTo.trim()} className={btnSecondary}>
                  <PhoneForwarded className="h-4 w-4" /> Transfer
                </button>
              </form>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={dial}
            disabled={!registered || !number.trim()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3 font-semibold text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Phone className="h-5 w-5" /> Call
          </button>
        )}

        {call?.error && onCall && (
          <button type="button" className={`${btnSecondary} w-full`} onClick={() => void sip.enableAudio()}>
            <Volume2 className="h-4 w-4" /> Enable audio
          </button>
        )}

        {sip.actionError && (
          <div className="flex items-start justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            <span>{sip.actionError}</span>
            <button type="button" className="font-medium underline" onClick={sip.clearActionError}>
              OK
            </button>
          </div>
        )}

        {sip.mode === "mock" && (
          <div className="border-t border-slate-100 pt-4">
            <button
              type="button"
              onClick={onSimulateIncoming}
              disabled={!registered || simulating}
              className={`${btnSecondary} w-full`}
            >
              {simulating ? <Spinner /> : <PhoneIncoming className="h-4 w-4" />} Simulate Incoming Call
            </button>
            <p className="mt-2 text-center text-[11px] leading-relaxed text-slate-400">
              Mock test numbers: …0000 fails · …1111 no answer · …2222 declined · others answer
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
