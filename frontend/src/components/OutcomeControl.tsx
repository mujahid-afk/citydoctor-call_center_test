import { Check, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { CALL_OUTCOMES, api, type Call, type CallOutcome } from "../api";
import { humanize } from "../lib/format";
import { ErrorBanner, Spinner, btnPrimary, btnSecondary, inputClass, labelClass } from "./ui";

// Fetched once per page load: is OPENAI_API_KEY configured on the backend?
let aiStatusPromise: Promise<boolean> | null = null;
function aiAvailable(): Promise<boolean> {
  aiStatusPromise ??= api.aiStatus().then((s) => s.enabled).catch(() => false);
  return aiStatusPromise;
}

/** Pick + save a call outcome (POST /api/calls/{id}/outcome). */
export function OutcomeControl({
  callId,
  initialOutcome,
  initialNotes,
  onSaved,
  onSummarized,
}: {
  callId: number | null;
  initialOutcome: CallOutcome | null;
  initialNotes: string | null;
  onSaved: (call: Call) => void;
  /** Called after an AI summary was generated and stored on the call. */
  onSummarized?: (call: Call) => void;
}) {
  const [outcome, setOutcome] = useState<CallOutcome | null>(initialOutcome);
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [ai, setAi] = useState<{ summary: string; next: string } | null>(null);

  useEffect(() => {
    setOutcome(initialOutcome);
    setNotes(initialNotes ?? "");
    setSaved(false);
  }, [callId, initialOutcome, initialNotes]);

  useEffect(() => {
    setAi(null);
  }, [callId]);

  useEffect(() => {
    void aiAvailable().then(setAiEnabled);
  }, []);

  const summarize = async () => {
    if (!callId) return;
    setAiBusy(true);
    setError(null);
    try {
      const result = await api.aiSummary(callId, notes || null);
      setAi({ summary: result.summary, next: result.next_action });
      if (result.suggested_outcome) {
        setOutcome(result.suggested_outcome);
        setSaved(false);
      }
      onSummarized?.(result.call);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  };

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
      {ai && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-slate-800">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-violet-700">
            <Sparkles className="h-3.5 w-3.5" /> AI summary (saved to call)
          </p>
          <p>{ai.summary || "No summary returned."}</p>
          {ai.next && <p className="mt-1 text-xs text-slate-600">Next: {ai.next}</p>}
          <p className="mt-1 text-[11px] text-slate-500">Suggested outcome is pre-selected above - review it, then Save outcome.</p>
        </div>
      )}
      {error && <ErrorBanner message={error} />}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnPrimary} disabled={!callId || !outcome || saving} onClick={() => void save()}>
          {saving ? <Spinner /> : saved ? <Check className="h-4 w-4" /> : null}
          {saved ? "Outcome saved" : "Save outcome"}
        </button>
        {aiEnabled && (
          <button type="button" className={btnSecondary} disabled={!callId || aiBusy} onClick={() => void summarize()}>
            {aiBusy ? <Spinner /> : <Sparkles className="h-4 w-4 text-violet-600" />} AI summary
          </button>
        )}
      </div>
      {!callId && <p className="text-xs text-slate-400">Waiting for the call record…</p>}
    </div>
  );
}
