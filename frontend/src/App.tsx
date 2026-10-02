import { Menu, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { api, type Booking, type Brand, type Call, type CallFilters, type Stats } from "./api";
import { ActiveCallPanel } from "./components/ActiveCallPanel";
import { BookingModal, type BookingTarget } from "./components/BookingModal";
import { BookingsSection } from "./components/BookingsSection";
import { CallDetailsModal } from "./components/CallDetailsModal";
import { EMPTY_FILTERS, FiltersBar, type FilterState } from "./components/FiltersBar";
import { InboundCallsTable } from "./components/InboundCallsTable";
import { IncomingCallModal } from "./components/IncomingCallModal";
import { OutboundCallsTable } from "./components/OutboundCallsTable";
import { SettingsPanel } from "./components/SettingsPanel";
import { Sidebar, type SectionId } from "./components/Sidebar";
import { SoftPhone } from "./components/SoftPhone";
import { StatsCards } from "./components/StatsCards";
import { Card, CardHeader, Toasts, type ToastMessage } from "./components/ui";
import { endOfDayIso, startOfDayIso, timeAgo } from "./lib/format";
import { useCallLogger } from "./lib/useCallLogger";
import { SipProvider, useSip, type SipCallEvent } from "./webrtc/SipContext";

const POLL_MS = 5000;

type Handler = (event: SipCallEvent) => void;

export default function App() {
  // The logger lives inside <Dashboard> (it needs SIP info); the provider forwards events to it.
  const handlerRef = useRef<Handler | null>(null);
  const onCallEvent = useCallback((event: SipCallEvent) => handlerRef.current?.(event), []);
  return (
    <SipProvider onCallEvent={onCallEvent}>
      <Dashboard handlerRef={handlerRef} />
    </SipProvider>
  );
}

function toApiFilters(f: FilterState): CallFilters {
  return {
    search: f.search.trim(),
    direction: f.direction,
    brand_id: f.brandId,
    status: f.status,
    outcome: f.outcome,
    date_from: f.dateFrom ? startOfDayIso(f.dateFrom) : undefined,
    date_to: f.dateTo ? endOfDayIso(f.dateTo) : undefined,
  };
}

function Dashboard({ handlerRef }: { handlerRef: MutableRefObject<Handler | null> }) {
  const sip = useSip();
  const [brands, setBrands] = useState<Brand[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [inbound, setInbound] = useState<Call[] | null>(null);
  const [outbound, setOutbound] = useState<Call[] | null>(null);
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [refreshKey, setRefreshKey] = useState(0);

  const [number, setNumber] = useState("");
  const [simulating, setSimulating] = useState(false);
  const [detailsId, setDetailsId] = useState<number | null>(null);
  const [bookingTarget, setBookingTarget] = useState<BookingTarget | null>(null);
  const [activeSection, setActiveSection] = useState<SectionId>("dashboard");
  const [menuOpen, setMenuOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const toast = useCallback((kind: ToastMessage["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  // ------------------------------------------------------------------ data loading
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const refresh = useCallback(async () => {
    const f = toApiFilters(filtersRef.current);
    const showInbound = f.direction !== "outbound";
    const showOutbound = f.direction !== "inbound";
    try {
      const [s, inb, outb, bk] = await Promise.all([
        api.stats(f),
        showInbound ? api.calls({ ...f, direction: "inbound" }) : Promise.resolve([]),
        showOutbound ? api.calls({ ...f, direction: "outbound" }) : Promise.resolve([]),
        api.bookings(),
      ]);
      setStats(s);
      setInbound(inb);
      setOutbound(outb);
      setBookings(bk);
      setLoadError(null);
      setBackendOk(true);
      setLastUpdated(new Date());
    } catch (error) {
      setLoadError((error as Error).message);
      setBackendOk(false);
    }
  }, []);

  const changed = useCallback(() => {
    setRefreshKey((k) => k + 1);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    api.brands().then(setBrands).catch((e: Error) => setLoadError(e.message));
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void refresh(), 250); // debounce typing in search
    return () => clearTimeout(timer);
  }, [filters, refresh]);

  useEffect(() => {
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  // ------------------------------------------------------------------ call logging
  const { handleEvent, crmIds } = useCallLogger({
    extension: sip.extension,
    mock: sip.mode !== "real",
    onChange: changed,
    onError: (message) => toast("error", message),
  });
  handlerRef.current = handleEvent;

  // ------------------------------------------------------------------ actions
  const navigate = (id: SectionId) => {
    setActiveSection(id);
    setMenuOpen(false);
    if (id === "dashboard") window.scrollTo({ top: 0, behavior: "smooth" });
    else document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const dialFromCrm = (phone: string) => {
    setNumber(phone);
    document.getElementById("softphone")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const simulateIncoming = async () => {
    setSimulating(true);
    try {
      const caller = await api.randomCaller();
      sip.simulateIncomingCall(caller.customer_phone, caller.brand_number ?? undefined, caller.customer_name ?? undefined);
    } catch (error) {
      toast("error", (error as Error).message);
    } finally {
      setSimulating(false);
    }
  };

  const openBookingForPhone = async (callId: number | null, phone: string) => {
    const lookup = await api.customerByPhone(phone).catch(() => null);
    const call = callId ? await api.call(callId).catch(() => null) : null;
    if (!lookup) toast("info", "Unknown customer - create the customer first, or pick one in the booking form.");
    setBookingTarget({ customerId: lookup?.customer.id ?? null, callId, brandName: call?.brand_name ?? null });
  };

  const showInbound = filters.direction !== "outbound";
  const showOutbound = filters.direction !== "inbound";

  return (
    <div className="min-h-screen bg-slate-50">
      <Sidebar
        active={activeSection}
        onNavigate={navigate}
        sipMode={sip.mode}
        registration={sip.registration}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <div className="lg:pl-64">
        {/* Mobile top bar */}
        <div className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 lg:hidden">
          <button type="button" onClick={() => setMenuOpen(true)} className="rounded p-1 text-slate-600" aria-label="Open menu">
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-semibold text-slate-900">Voice Call CRM</span>
        </div>

        <main className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-6 lg:p-8">
          <header id="dashboard" className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Voice Call CRM</h1>
              <p className="text-sm text-slate-500">Inbound &amp; Outbound AI Calling</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {sip.mode === "mock" && (
                <span className="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-700 ring-1 ring-amber-200">Mock SIP mode</span>
              )}
              <span className={`h-2 w-2 rounded-full ${loadError ? "bg-red-500" : "bg-emerald-500"}`} />
              {loadError ? "Backend unreachable" : `Live · updated ${timeAgo(lastUpdated)}`}
            </div>
          </header>

          {loadError && !stats && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {loadError} Start it with <code className="font-mono">uvicorn app.main:app --reload --port 8000</code> in <code>backend/</code>.
            </div>
          )}

          <StatsCards stats={stats} loading={!stats && !loadError} />

          <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
            <SoftPhone brands={brands} number={number} onNumberChange={setNumber} onSimulateIncoming={() => void simulateIncoming()} simulating={simulating} />
            <ActiveCallPanel
              brands={brands}
              crmIds={crmIds}
              refreshKey={refreshKey}
              onDial={dialFromCrm}
              onCustomerCreated={(c) => {
                toast("success", `Customer ${c.name} created`);
                changed();
              }}
              onOpenCall={setDetailsId}
              onBook={(callId, phone) => void openBookingForPhone(callId, phone)}
              onSummarized={(c) => {
                toast("success", `AI summary saved for call #${c.id}`);
                changed();
              }}
              onOutcomeSaved={(c) => {
                toast("success", `Outcome saved for call #${c.id}`);
                changed();
              }}
            />
          </div>

          <FiltersBar value={filters} onChange={setFilters} brands={brands} />

          {showInbound && (
            <Card id="inbound">
              <CardHeader icon={<PhoneIncoming className="h-4 w-4" />} title="Inbound Calls" subtitle={inbound ? `${inbound.length} calls` : "Loading…"} />
              <InboundCallsTable calls={inbound} error={loadError} onRetry={() => void refresh()} onOpen={(c) => setDetailsId(c.id)} onDial={dialFromCrm} />
            </Card>
          )}

          {showOutbound && (
            <Card id="outbound">
              <CardHeader icon={<PhoneOutgoing className="h-4 w-4" />} title="Outbound Calls" subtitle={outbound ? `${outbound.length} calls` : "Loading…"} />
              <OutboundCallsTable calls={outbound} error={loadError} onRetry={() => void refresh()} onOpen={(c) => setDetailsId(c.id)} onDial={dialFromCrm} />
            </Card>
          )}

          <BookingsSection
            bookings={bookings}
            error={loadError}
            onRetry={() => void refresh()}
            onNew={() => setBookingTarget({})}
            onOpenCall={setDetailsId}
            onChanged={changed}
          />

          <SettingsPanel backendOk={backendOk} />
        </main>
      </div>

      <IncomingCallModal brands={brands} />

      <CallDetailsModal
        callId={detailsId}
        refreshKey={refreshKey}
        onClose={() => setDetailsId(null)}
        onDial={dialFromCrm}
        onBook={(call) => setBookingTarget({ customerId: call.customer_id, callId: call.id, brandName: call.brand_name })}
        onChanged={changed}
      />

      <BookingModal
        target={bookingTarget}
        onClose={() => setBookingTarget(null)}
        onBooked={(booking) => {
          setBookingTarget(null);
          toast("success", `Booking ${booking.reference} confirmed for ${booking.appointment_date} ${booking.appointment_time}`);
          changed();
        }}
      />

      <Toasts toasts={toasts} onDismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />
    </div>
  );
}
