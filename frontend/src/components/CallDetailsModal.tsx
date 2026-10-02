import { CalendarPlus, Phone } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, type Call } from "../api";
import { formatDateTime, formatDuration, humanize } from "../lib/format";
import { OutcomeControl } from "./OutcomeControl";
import { DirectionBadge, ErrorBanner, Modal, OutcomeBadge, Spinner, StatusBadge, btnSecondary } from "./ui";

function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-slate-900">{children ?? <span className="text-slate-400">—</span>}</dd>
    </div>
  );
}

const orDash = (v: string | null | undefined) => v || <span className="text-slate-400">—</span>;

function Transcript({ text }: { text: string }) {
  return (
    <div className="max-h-72 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
      {text.split("\n").filter(Boolean).map((line, i) => {
        const match = line.match(/^(AI|Agent|Customer|User):\s*(.*)$/i);
        const isAgent = match ? /^(ai|agent)$/i.test(match[1]) : false;
        return (
          <div key={i} className={`flex ${isAgent ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${isAgent ? "bg-white text-slate-800 shadow-sm" : "bg-blue-600 text-white"}`}>
              {match && <p className={`text-[10px] font-semibold uppercase ${isAgent ? "text-slate-400" : "text-blue-100"}`}>{match[1]}</p>}
              {match ? match[2] : line}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function CallDetailsModal({
  callId,
  refreshKey,
  onClose,
  onDial,
  onBook,
  onChanged,
}: {
  callId: number | null;
  refreshKey: number;
  onClose: () => void;
  onDial: (phone: string) => void;
  onBook: (call: Call) => void;
  onChanged: () => void;
}) {
  const [call, setCall] = useState<Call | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!callId) {
      setCall(null);
      return;
    }
    let cancelled = false;
    api
      .call(callId)
      .then((c) => !cancelled && (setCall(c), setError(null)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [callId, refreshKey]);

  const audioUrl = call?.recording_url && /^https?:\/\//.test(call.recording_url) ? call.recording_url : null;

  return (
    <Modal
      open={callId !== null}
      onClose={onClose}
      size="xl"
      title={call ? `${call.customer_name ?? "Unknown customer"} · ${call.customer_phone}` : "Call details"}
      subtitle={call && <span className="flex flex-wrap items-center gap-2">Call #{call.id} <DirectionBadge direction={call.direction} /> <StatusBadge status={call.status} /> <OutcomeBadge outcome={call.outcome} /></span>}
      footer={
        call && (
          <>
            <button type="button" className={btnSecondary} onClick={() => onBook(call)}>
              <CalendarPlus className="h-4 w-4" /> Create booking
            </button>
            <button type="button" className={btnSecondary} onClick={() => { onDial(call.customer_phone); onClose(); }}>
              <Phone className="h-4 w-4" /> {call.direction === "inbound" ? "Call back" : "Redial"}
            </button>
          </>
        )
      }
    >
      {error && !call && <ErrorBanner message={error} />}
      {!call && !error && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> Loading call…</div>}
      {call && (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-5 lg:col-span-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
              <Field label="Direction">{humanize(call.direction)}</Field>
              <Field label="Customer">{orDash(call.customer_name)}</Field>
              <Field label="Phone">{call.customer_phone}</Field>
              <Field label="Brand">{orDash(call.brand_name)}</Field>
              <Field label="Brand Number">{orDash(call.brand_number)}</Field>
              <Field label="SIP Extension">{orDash(call.sip_extension)}</Field>
              <Field label="Call Status"><StatusBadge status={call.status} /></Field>
              <Field label="Call Outcome"><OutcomeBadge outcome={call.outcome} /></Field>
              <Field label="Purpose">{orDash(call.purpose)}</Field>
              <Field label="Started At">{formatDateTime(call.started_at)}</Field>
              <Field label="Answered At">{formatDateTime(call.answered_at)}</Field>
              <Field label="Ended At">{formatDateTime(call.ended_at)}</Field>
              <Field label="Duration">{formatDuration(call.duration_seconds)}</Field>
              <Field label="Booking">{orDash(call.booking_reference)}</Field>
              <Field label="Mock / test">{call.is_mock ? "Yes" : "No"}</Field>
              <Field label="ElevenLabs Conversation ID" wide><span className="font-mono text-xs">{orDash(call.elevenlabs_conversation_id)}</span></Field>
              <Field label="SIP Call ID"><span className="font-mono text-xs">{orDash(call.sip_call_id)}</span></Field>
              <Field label="Notes" wide>{orDash(call.notes)}</Field>
            </dl>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">AI Summary</p>
              {call.summary ? <p className="rounded-lg bg-blue-50 p-3 text-sm text-slate-800">{call.summary}</p> : <p className="text-sm text-slate-400">No summary (added later via PATCH /api/calls/{call.id}).</p>}
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Transcript</p>
              {call.transcript ? <Transcript text={call.transcript} /> : <p className="text-sm text-slate-400">No transcript.</p>}
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Recording</p>
              {call.recording_url ? (
                <div className="space-y-2">
                  {audioUrl && <audio controls src={audioUrl} className="w-full" />}
                  <a href={call.recording_url} target="_blank" rel="noreferrer" className="break-all text-sm text-blue-600 underline">{call.recording_url}</a>
                </div>
              ) : (
                <p className="text-sm text-slate-400">No recording URL.</p>
              )}
            </div>
          </div>
          <div className="lg:col-span-2">
            <div className="rounded-xl border border-slate-200 p-4">
              <OutcomeControl
                callId={call.id}
                initialOutcome={call.outcome}
                initialNotes={call.notes}
                onSaved={(updated) => {
                  setCall(updated);
                  onChanged();
                }}
                onSummarized={(updated) => {
                  setCall(updated);
                  onChanged();
                }}
              />
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
