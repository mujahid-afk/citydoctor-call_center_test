import { CalendarCheck, Phone, Search, UserPlus, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Customer, type CustomerLookup } from "../api";
import { formatDateTime, formatDuration } from "../lib/format";
import { EmptyState, ErrorBanner, OutcomeBadge, Spinner, StatusBadge, btnGhost, btnPrimary, inputClass, labelClass } from "./ui";

/** Customer info for a phone number (lookup + create), or a searchable list when no number is given. */
export function CustomerPanel({
  phone,
  refreshKey,
  onDial,
  onCustomerCreated,
  onOpenCall,
}: {
  phone: string | null;
  refreshKey: number;
  onDial: (phone: string) => void;
  onCustomerCreated: (customer: Customer) => void;
  onOpenCall: (id: number) => void;
}) {
  return phone ? (
    <CustomerLookupView phone={phone} refreshKey={refreshKey} onCreated={onCustomerCreated} onOpenCall={onOpenCall} />
  ) : (
    <CustomerSearch refreshKey={refreshKey} onDial={onDial} />
  );
}

function CustomerLookupView({
  phone,
  refreshKey,
  onCreated,
  onOpenCall,
}: {
  phone: string;
  refreshKey: number;
  onCreated: (customer: Customer) => void;
  onOpenCall: (id: number) => void;
}) {
  const [lookup, setLookup] = useState<CustomerLookup | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", email: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api
      .customerByPhone(phone)
      .then((result) => {
        setLookup(result);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [phone]);

  useEffect(() => {
    setLookup(undefined);
    load();
  }, [load]);

  useEffect(() => {
    if (refreshKey) load();
  }, [refreshKey, load]);

  const create = async () => {
    setSaving(true);
    setError(null);
    try {
      const customer = await api.createCustomer({ name: form.name, phone, email: form.email || null });
      onCreated(customer);
      setForm({ name: "", email: "" });
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (error && lookup === undefined) return <ErrorBanner message={error} onRetry={load} />;
  if (lookup === undefined) {
    return (
      <div className="flex items-center gap-2 p-5 text-sm text-slate-500">
        <Spinner /> Looking up {phone}…
      </div>
    );
  }

  if (lookup === null) {
    return (
      <div className="space-y-4 p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-slate-100 p-2.5 text-slate-400">
            <UserRound className="h-5 w-5" />
          </div>
          <div>
            <p className="font-semibold text-slate-900">Unknown Customer</p>
            <p className="text-sm text-slate-500">{phone}</p>
          </div>
        </div>
        <div className="space-y-3 rounded-lg border border-dashed border-slate-300 p-4">
          <p className="text-sm font-medium text-slate-700">Create Customer</p>
          <div>
            <label className={labelClass}>Name</label>
            <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Full name" />
          </div>
          <div>
            <label className={labelClass}>Email (optional)</label>
            <input className={inputClass} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@example.com" />
          </div>
          {error && <ErrorBanner message={error} />}
          <button type="button" className={btnPrimary} disabled={!form.name.trim() || saving} onClick={() => void create()}>
            {saving ? <Spinner /> : <UserPlus className="h-4 w-4" />} Create Customer
          </button>
        </div>
      </div>
    );
  }

  const { customer, recent_calls, bookings } = lookup;
  return (
    <div className="space-y-4 p-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
          {customer.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
        </div>
        <div>
          <p className="font-semibold text-slate-900">{customer.name}</p>
          <p className="text-sm text-slate-500">
            {customer.phone}
            {customer.email ? ` · ${customer.email}` : ""}
          </p>
        </div>
      </div>
      {customer.notes && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{customer.notes}</p>}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Previous calls ({recent_calls.length})</p>
        {recent_calls.length === 0 ? (
          <p className="text-sm text-slate-400">No previous calls.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-100">
            {recent_calls.slice(0, 5).map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => onOpenCall(c.id)} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-slate-50">
                  <span className="text-slate-600">
                    {formatDateTime(c.started_at)} · {c.direction} · {formatDuration(c.duration_seconds)}
                  </span>
                  <span className="flex gap-1">
                    <StatusBadge status={c.status} />
                    <OutcomeBadge outcome={c.outcome} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Bookings ({bookings.length})</p>
        {bookings.length === 0 ? (
          <p className="text-sm text-slate-400">No bookings.</p>
        ) : (
          <ul className="space-y-1.5">
            {bookings.slice(0, 4).map((b) => (
              <li key={b.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <CalendarCheck className="h-3.5 w-3.5 text-blue-600" />
                  {b.reference} · {b.service}
                </span>
                <span className="text-slate-500">
                  {b.appointment_date} {b.appointment_time} · {b.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CustomerSearch({ refreshKey, onDial }: { refreshKey: number; onDial: (phone: string) => void }) {
  const [search, setSearch] = useState("");
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      api
        .customers(search || undefined)
        .then((list) => {
          setCustomers(list);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [search, refreshKey]);

  return (
    <div className="p-5">
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input className={`${inputClass} pl-9`} placeholder="Search customers by name or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {error && <ErrorBanner message={error} />}
      {customers === null ? (
        <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
          <Spinner /> Loading customers…
        </div>
      ) : customers.length === 0 ? (
        <EmptyState title="No customers found" description="Try another name or number." />
      ) : (
        <ul className="max-h-[420px] divide-y divide-slate-100 overflow-y-auto">
          {customers.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{c.name}</p>
                <p className="text-xs text-slate-500">{c.phone}</p>
              </div>
              <button type="button" className={btnGhost} onClick={() => onDial(c.phone)}>
                <Phone className="h-3.5 w-3.5" /> Dial
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
