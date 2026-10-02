import { Phone, PhoneIncoming, PhoneOff } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Brand, type CustomerLookup } from "../api";
import { useSip } from "../webrtc/SipContext";
import { Spinner } from "./ui";

export function matchBrand(brands: Brand[], number?: string | null): Brand | undefined {
  const digits = (number ?? "").replace(/\D/g, "").slice(-9);
  if (!digits) return undefined;
  return brands.find((b) => b.phone_number.replace(/\D/g, "").slice(-9) === digits);
}

export function IncomingCallModal({ brands }: { brands: Brand[] }) {
  const sip = useSip();
  const call = sip.call?.state === "incoming" ? sip.call : null;
  const [lookup, setLookup] = useState<CustomerLookup | null | undefined>(undefined);
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
  const brand = matchBrand(brands, call.calledNumber);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="alertdialog" aria-modal>
      <div className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="bg-slate-900 px-6 py-6 text-center text-white">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/20">
            <PhoneIncoming className="h-7 w-7 animate-pulse text-emerald-400" />
          </div>
          <p className="text-xs uppercase tracking-wider text-slate-400">Incoming call · inbound</p>
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
            <dd className="font-medium text-slate-900">{brand?.name ?? "Unknown brand"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Called number</dt>
            <dd className="font-medium text-slate-900">{call.calledNumber ?? "—"}</dd>
          </div>
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
