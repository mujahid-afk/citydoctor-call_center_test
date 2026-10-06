import { CalendarPlus, PhoneIncoming, PhoneOutgoing, Users, X } from "lucide-react";
import type { Brand, Call, Customer, Queue } from "../api";
import { formatDuration, humanize } from "../lib/format";
import { brandForCall } from "../lib/routing";
import { useNow } from "../lib/useNow";
import { useSip } from "../webrtc/SipContext";
import type { SipCall } from "../webrtc/types";
import { CustomerPanel } from "./CustomerPanel";
import { OutcomeControl } from "./OutcomeControl";
import { btnGhost, btnSecondary } from "./ui";

const END_LABEL: Record<string, string> = {
  completed: "Completed",
  rejected: "Rejected",
  missed: "Missed / no answer",
  busy_rejected: "Missed (busy)",
  failed: "Failed",
};

export function ActiveCallPanel({
  brands,
  queues,
  crmIds,
  refreshKey,
  onDial,
  onCustomerCreated,
  onOpenCall,
  onBook,
  onOutcomeSaved,
  onSummarized,
}: {
  brands: Brand[];
  queues: Queue[];
  crmIds: Record<string, number>;
  refreshKey: number;
  onDial: (phone: string) => void;
  onCustomerCreated: (customer: Customer) => void;
  onOpenCall: (id: number) => void;
  onBook: (callId: number | null, phone: string) => void;
  onOutcomeSaved: (call: Call) => void;
  onSummarized?: (call: Call) => void;
}) {
  const sip = useSip();
  const live = sip.call;
  const ended = live ? null : sip.lastEndedCall;
  const shown: SipCall | null = live ?? ended;
  const now = useNow(live?.state === "answered");

  if (!shown) {
    return (
      <section id="customers" className="scroll-mt-20 rounded-xl border border-slate-200 bg-white shadow-sm">
        <Header icon={<Users className="h-4 w-4" />} title="Customers" subtitle="Search and click Dial to call" />
        <CustomerPanel phone={null} refreshKey={refreshKey} onDial={onDial} onCustomerCreated={onCustomerCreated} onOpenCall={onOpenCall} />
      </section>
    );
  }

  const crmId = crmIds[shown.id] ?? null;
  const brand = brandForCall(brands, queues, shown);
  const brandName = brand?.name ?? shown.brandLabel;
  const talk = shown.answeredAt ? Math.floor(((shown.endedAt ?? now) - shown.answeredAt) / 1000) : 0;

  return (
    <section id="customers" className="scroll-mt-20 rounded-xl border border-slate-200 bg-white shadow-sm">
      <Header
        icon={shown.direction === "inbound" ? <PhoneIncoming className="h-4 w-4" /> : <PhoneOutgoing className="h-4 w-4" />}
        title={live ? "Active Call" : "Call Wrap-up"}
        subtitle={[humanize(shown.direction), shown.remoteNumber, brandName, shown.queueName, crmId && `CRM #${crmId}`].filter(Boolean).join(" · ")}
        action={
          ended && (
            <button type="button" className={btnGhost} onClick={sip.dismissLastCall}>
              <X className="h-3.5 w-3.5" /> Done
            </button>
          )
        }
      />
      <div className="grid grid-cols-3 gap-3 border-b border-slate-100 px-5 py-3 text-sm">
        <div>
          <p className="text-xs text-slate-500">State</p>
          <p className="font-medium text-slate-900">{live ? humanize(live.state === "answered" ? "on_call" : live.state) : END_LABEL[shown.endReason ?? "completed"]}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Talk time</p>
          <p className="font-mono font-medium tabular-nums text-slate-900">{formatDuration(talk)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">SIP Call-ID</p>
          <p className="truncate font-mono text-xs text-slate-700" title={shown.sipCallId}>{shown.sipCallId ?? "—"}</p>
        </div>
        {shown.error && <p className="col-span-3 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{shown.error}</p>}
      </div>

      {ended && (
        <div className="space-y-3 border-b border-slate-100 px-5 py-4">
          <OutcomeControl callId={crmId} initialOutcome={null} initialNotes={null} onSaved={onOutcomeSaved} onSummarized={onSummarized} />
          <button type="button" className={btnSecondary} onClick={() => onBook(crmId, shown.remoteNumber)}>
            <CalendarPlus className="h-4 w-4" /> Book appointment
          </button>
        </div>
      )}

      <CustomerPanel phone={shown.remoteNumber} refreshKey={refreshKey} onDial={onDial} onCustomerCreated={onCustomerCreated} onOpenCall={onOpenCall} />
    </section>
  );
}

function Header({ icon, title, subtitle, action }: { icon: React.ReactNode; title: string; subtitle: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="rounded-lg bg-blue-50 p-2 text-blue-600">{icon}</div>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <p className="truncate text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>
      {action}
    </div>
  );
}
