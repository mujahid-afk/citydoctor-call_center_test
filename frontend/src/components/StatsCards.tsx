import {
  CalendarCheck,
  Clock,
  PhoneCall,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  Phone,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { Stats } from "../api";
import { formatDuration } from "../lib/format";

interface Item {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone: string;
}

export function StatsCards({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const s = stats;
  const items: Item[] = [
    { label: "Total Calls", value: s?.total_calls ?? 0, icon: Phone, tone: "bg-slate-100 text-slate-600" },
    { label: "Inbound Calls", value: s?.inbound_calls ?? 0, icon: PhoneIncoming, tone: "bg-cyan-50 text-cyan-600" },
    { label: "Outbound Calls", value: s?.outbound_calls ?? 0, icon: PhoneOutgoing, tone: "bg-blue-50 text-blue-600" },
    { label: "Answered", value: s?.answered ?? 0, icon: PhoneCall, tone: "bg-emerald-50 text-emerald-600" },
    { label: "Missed", value: s?.missed ?? 0, icon: PhoneMissed, tone: "bg-orange-50 text-orange-600" },
    { label: "Failed", value: s?.failed ?? 0, icon: TriangleAlert, tone: "bg-red-50 text-red-600" },
    { label: "Bookings", value: s?.bookings ?? 0, icon: CalendarCheck, tone: "bg-indigo-50 text-indigo-600" },
    { label: "Average Duration", value: formatDuration(s?.average_duration_seconds ?? 0), icon: Clock, tone: "bg-violet-50 text-violet-600" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 2xl:grid-cols-8">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-medium text-slate-500">{item.label}</p>
              <div className={`rounded-lg p-1.5 ${item.tone}`}>
                <Icon className="h-4 w-4" />
              </div>
            </div>
            {loading ? (
              <div className="mt-2 h-7 w-12 animate-pulse rounded bg-slate-100" />
            ) : (
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{item.value}</p>
            )}
            {item.label === "Total Calls" && !!s?.in_progress && (
              <p className="mt-0.5 text-[11px] text-blue-600">{s.in_progress} in progress</p>
            )}
            {item.label === "Inbound Calls" && !!s?.average_wait_seconds && (
              <p className="mt-0.5 text-[11px] text-slate-500" title="Average wait of answered inbound calls">
                avg wait {formatDuration(s.average_wait_seconds)}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
