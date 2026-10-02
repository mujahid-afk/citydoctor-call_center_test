import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { CALL_OUTCOMES, api, type Call, type CallOutcome } from "../api";
import { humanize } from "../lib/format";
import { ErrorBanner, Spinner, btnPrimary, inputClass, labelClass } from "./ui";

/** Pick + save a call outcome (POST /api/calls/{id}/outcome). */
export function OutcomeControl({
  callId,
  initialOutcome,
  initialNotes,
  onSaved,
}: {
  callId: number | null;
  initialOutcome: CallOutcome | null;
  initialNotes: string | null;
  onSaved: (call: Call) => void;
}) {
  const [outcome, setOutcome] = useState<CallOutcome | null>(initialOutcome);
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOutcome(initialOutcome);
    setNotes(initialNotes ?? "");
    setSaved(false);
  }, [callId, initialOutcome, initialNotes]);

  const save = async () => {
    if (!callId || !outcome) return;
    setSaving(true);
    setError(null);
    try {
      const call = await api.saveOutcome(callId, outcome, notes || null);
      setSaved(true);
      onSaved(call);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <p className={labelClass}>Call outcome</p>
        <div className="flex flex-wrap gap-1.5">
          {CALL_OUTCOMES.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setOutcome(value);
                setSaved(false);
              }}
              className={`rounded-lg border px-2 py-1.5 text-xs font-medium ${
                outcome === value ? "border-blue-600 bg-blue-600 text-white" : "border-slate-200 bg-white text-slate-700 hover:border-blue-300"
              }`}
            >
              {humanize(value)}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className={labelClass}>Notes</label>
        <textarea className={inputClass} rows={2} value={notes} onChange={(e) => { setNotes(e.target.value); setSaved(false); }} placeholder="What happened on the call?" />
      </div>
      {error && <ErrorBanner message={error} />}
      <button type="button" className={btnPrimary} disabled={!callId || !outcome || saving} onClick={() => void save()}>
        {saving ? <Spinner /> : saved ? <Check className="h-4 w-4" /> : null}
        {saved ? "Outcome saved" : "Save outcome"}
      </button>
      {!callId && <p className="text-xs text-slate-400">Waiting for the call record…</p>}
    </div>
  );
}
