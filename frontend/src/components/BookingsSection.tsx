import { CalendarCheck, Plus } from "lucide-react";
import { api, type Booking } from "../api";
import { humanize } from "../lib/format";
import { Card, CardHeader, EmptyState, ErrorBanner, TableSkeleton, btnGhost, btnPrimary, td, th } from "./ui";

const STATUS_TONE: Record<Booking["status"], string> = {
  confirmed: "bg-emerald-50 text-emerald-700",
  rescheduled: "bg-amber-50 text-amber-700",
  cancelled: "bg-slate-100 text-slate-500",
  completed: "bg-blue-50 text-blue-700",
};

export function BookingsSection({
  bookings,
  error,
  onRetry,
  onNew,
  onOpenCall,
  onChanged,
}: {
  bookings: Booking[] | null;
  error: string | null;
  onRetry: () => void;
  onNew: () => void;
  onOpenCall: (id: number) => void;
  onChanged: () => void;
}) {
  const cancel = async (booking: Booking) => {
    await api.updateBooking(booking.id, { status: "cancelled" }).catch(() => undefined);
    onChanged();
  };
  return (
    <Card id="bookings">
      <CardHeader
        icon={<CalendarCheck className="h-4 w-4" />}
        title="Bookings"
        subtitle="Dummy booking API (SQLite)"
        actions={
          <button type="button" className={btnPrimary} onClick={onNew}>
            <Plus className="h-4 w-4" /> New Booking
          </button>
        }
      />
      {error && !bookings ? (
        <div className="p-5"><ErrorBanner message={error} onRetry={onRetry} /></div>
      ) : !bookings ? (
        <TableSkeleton cols={6} />
      ) : bookings.length === 0 ? (
        <EmptyState title="No bookings yet" description="Book an appointment after a call or with New Booking." />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50">
              <tr>
                {["Reference", "Customer", "Service", "Date", "Time", "Status", "Call", "Actions"].map((h) => <th key={h} className={th}>{h}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {bookings.map((b) => (
                <tr key={b.id}>
                  <td className={`${td} font-medium text-blue-700`}>{b.reference}</td>
                  <td className={td}>{b.customer_name ?? "—"}</td>
                  <td className={td}>{b.service}</td>
                  <td className={td}>{b.appointment_date}</td>
                  <td className={td}>{b.appointment_time}</td>
                  <td className={td}><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[b.status]}`}>{humanize(b.status)}</span></td>
                  <td className={td}>
                    {b.call_id ? <button type="button" className={btnGhost} onClick={() => onOpenCall(b.call_id!)}>Call #{b.call_id}</button> : "—"}
                  </td>
                  <td className={td}>
                    {b.status !== "cancelled" && <button type="button" className={btnGhost} onClick={() => void cancel(b)}>Cancel</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
