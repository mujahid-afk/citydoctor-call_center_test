import { Phone, PhoneIncoming, PhoneOff } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Brand, type CustomerLookup, type Queue } from "../api";
import { formatDuration } from "../lib/format";
import { brandForCall, findQueue } from "../lib/routing";
import { useNow } from "../lib/useNow";
import { useSip } from "../webrtc/SipContext";
import { Spinner } from "./ui";

export function IncomingCallModal({ brands, queues }: { brands: Brand[]; queues: Queue[] }) {
  const sip = useSip();
  const call = sip.call?.state === "incoming" ? sip.call : null;
  const [lookup, setLookup] = useState<CustomerLookup | null | undefined>(undefined);
  const now = useNow(Boolean(call));
  const phone = call?.remoteNumber;

  useEffect(() => {
    setLookup(undefined);
    if (!phone) return;
    let cancelled = false;
    api
      .customerByPhone(phone)
      .then((result) => !cancelled && setLookup(result))
      .catch(() => !cancelled && setLookup(null));
    return () => {
      cancelled = true;
    };
  }, [phone]);

  if (!call) return null;
  const brand = brandForCall(brands, queues, call);
  const queue = findQueue(queues, call.queueName);
  // Without X-Queue-Start we only know how long our phone has been ringing.
  const waited = Math.max(0, Math.floor((now - (call.queueEnteredAt ?? call.startedAt)) / 1000));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="alertdialog" aria-modal>
      <div className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="bg-slate-900 px-6 py-6 text-center text-white">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/20">
            <PhoneIncoming className="h-7 w-7 animate-pulse text-emerald-400" />
          </div>
          <p className="text-xs uppercase tracking-wider text-slate-400">
            Incoming call · {brand?.name ?? call.brandLabel ?? "inbound"}
          </p>
          <p className="mt-1 text-2xl font-semibold">{call.remoteNumber}</p>
          <p className="mt-1 text-sm text-slate-300">
            {lookup === undefined ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3 w-3" /> Looking up customer…
              </span>
            ) : lookup ? (
              lookup.customer.name
            ) : (
              call.remoteDisplayName || "Unknown Customer"
            )}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-3 px-6 py-4 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Brand</dt>
            <dd className="font-medium text-slate-900">{brand?.name ?? call.brandLabel ?? "Unknown brand"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Queue</dt>
            <dd className="font-medium text-slate-900">
              {call.queueName ? (
                <>
                  {queue?.name ?? call.queueName}
                  {queue?.department && <span className="font-normal text-slate-500"> · {queue.department}</span>}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500" title={call.queueEnteredAt ? "Since the caller entered the queue" : "Since your phone started ringing"}>
              {call.queueEnteredAt ? "Waiting" : "Ringing"}
            </dt>
            <dd className={`font-mono font-medium tabular-nums ${waited >= 60 ? "text-orange-600" : "text-slate-900"}`}>{formatDuration(waited)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Called number</dt>
            <dd className="font-medium text-slate-900">{call.calledNumber ?? "—"}</dd>
          </div>
          {call.ivrPath && (
            <div className="col-span-2">
              <dt className="text-xs text-slate-500">IVR path</dt>
              <dd className="truncate font-mono text-xs text-slate-700" title={call.ivrPath}>{call.ivrPath}</dd>
            </div>
          )}
          {lookup && (
            <>
              <div>
                <dt className="text-xs text-slate-500">Previous calls</dt>
                <dd className="font-medium text-slate-900">{lookup.recent_calls.length}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Bookings</dt>
                <dd className="font-medium text-slate-900">{lookup.bookings.length}</dd>
              </div>
            </>
          )}
        </dl>
        <div className="grid grid-cols-2 gap-3 px-6 pb-6">
          <button type="button" onClick={() => void sip.answer()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-700">
            <Phone className="h-5 w-5" /> Answer
          </button>
          <button type="button" onClick={() => void sip.reject()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 py-3 font-semibold text-white hover:bg-red-700">
            <PhoneOff className="h-5 w-5" /> Reject
          </button>
        </div>
      </div>
    </div>
  );
}
