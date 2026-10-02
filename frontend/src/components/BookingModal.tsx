import { CalendarCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Booking, type Customer } from "../api";
import { localDateInput } from "../lib/format";
import { ErrorBanner, Modal, Spinner, btnPrimary, btnSecondary, inputClass, labelClass } from "./ui";

export const SERVICES = [
  "Doctor Consultation",
  "IV Drip Therapy",
  "Peptide Therapy Consultation",
  "Physiotherapy Session",
  "Women's Health Consultation",
  "Men's Health Consultation",
];

const BRAND_SERVICE: Record<string, string> = {
  "City Doctor": "Doctor Consultation",
  DripHub: "IV Drip Therapy",
  ProPeptides: "Peptide Therapy Consultation",
  PhysioHub: "Physiotherapy Session",
  "Girls Formula": "Women's Health Consultation",
  "Guys Formula": "Men's Health Consultation",
};

export interface BookingTarget {
  customerId?: number | null;
  callId?: number | null;
  brandName?: string | null;
}

export function BookingModal({
  target,
  onClose,
  onBooked,
}: {
  target: BookingTarget | null;
  onClose: () => void;
  onBooked: (booking: Booking) => void;
}) {
  const tomorrow = new Date(Date.now() + 86_400_000);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState<number | "">("");
  const [service, setService] = useState(SERVICES[0]);
  const [date, setDate] = useState(localDateInput(tomorrow));
  const [slots, setSlots] = useState<string[] | null>(null);
  const [time, setTime] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!target) return;
    setCustomerId(target.customerId ?? "");
    setService(BRAND_SERVICE[target.brandName ?? ""] ?? SERVICES[0]);
    setDate(localDateInput(new Date(Date.now() + 86_400_000)));
    setNotes("");
    setError(null);
    api.customers().then(setCustomers).catch((e: Error) => setError(e.message));
  }, [target]);

  useEffect(() => {
    if (!target || !date) return;
    setSlots(null);
    setTime("");
    api
      .availability(date, service)
      .then(setSlots)
      .catch((e: Error) => {
        setSlots([]);
        setError(e.message);
      });
  }, [target, date, service]);

  const submit = async () => {
    if (!customerId || !time) return;
    setSaving(true);
    setError(null);
    try {
      const booking = await api.createBooking({
        customer_id: customerId,
        call_id: target?.callId ?? null,
        service,
        appointment_date: date,
        appointment_time: time,
        notes: notes || null,
      });
      onBooked(booking);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={Boolean(target)}
      onClose={onClose}
      title="New Booking"
      subtitle={target?.callId ? `Linked to call #${target.callId}` : "Dummy booking API"}
      footer={
        <>
          <button type="button" className={btnSecondary} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={btnPrimary} disabled={!customerId || !time || saving} onClick={() => void submit()}>
            {saving ? <Spinner /> : <CalendarCheck className="h-4 w-4" />} Confirm Booking
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {customers.length === 0 && target?.customerId == null && (
          <p className="text-xs text-slate-500">Create the customer first if they are not in the list.</p>
        )}
        <div>
          <label className={labelClass}>Customer</label>
          <select className={inputClass} value={customerId} onChange={(e) => setCustomerId(Number(e.target.value) || "")}>
            <option value="">Select customer…</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.phone})
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Service</label>
            <select className={inputClass} value={service} onChange={(e) => setService(e.target.value)}>
              {SERVICES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Date</label>
            <input type="date" className={inputClass} value={date} min={localDateInput(new Date())} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        <div>
          <label className={labelClass}>Available slots</label>
          {slots === null ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> Checking availability…
            </div>
          ) : slots.length === 0 ? (
            <p className="text-sm text-slate-500">No free slots on this date.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {slots.map((slot) => (
                <button
                  key={slot}
                  type="button"
                  onClick={() => setTime(slot)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium ${
                    time === slot ? "border-blue-600 bg-blue-600 text-white" : "border-slate-200 bg-white text-slate-700 hover:border-blue-300"
                  }`}
                >
                  {slot}
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <label className={labelClass}>Notes</label>
          <textarea className={inputClass} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        {error && <ErrorBanner message={error} />}
      </div>
    </Modal>
  );
}
