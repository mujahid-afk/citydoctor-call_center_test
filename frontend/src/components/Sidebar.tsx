import {
  CalendarCheck,
  LayoutDashboard,
  MessageCircle,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  Settings,
  ChartColumn,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import type { RegistrationState, SipMode } from "../webrtc/types";

export type SectionId = "dashboard" | "inbound" | "outbound" | "customers" | "bookings" | "reports" | "settings";

interface Item {
  id: SectionId;
  label: string;
  icon: LucideIcon;
}

const VOICE_ITEMS: Item[] = [
  { id: "inbound", label: "Inbound Calls", icon: PhoneIncoming },
  { id: "outbound", label: "Outbound Calls", icon: PhoneOutgoing },
];

const REG_LABEL: Record<RegistrationState, string> = {
  disconnected: "Disconnected",
  connecting: "Connecting…",
  registered: "Registered",
  unregistered: "Unregistered",
  failed: "Registration failed",
};

export function Sidebar({
  active,
  onNavigate,
  sipMode,
  registration,
  open,
  onClose,
}: {
  active: SectionId;
  onNavigate: (id: SectionId) => void;
  sipMode: SipMode | null;
  registration: RegistrationState;
  open: boolean;
  onClose: () => void;
}) {
  const link = (item: Item, nested = false) => {
    const Icon = item.icon;
    const isActive = active === item.id;
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => onNavigate(item.id)}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          nested ? "pl-9" : ""
        } ${isActive ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
      >
        <Icon className="h-4 w-4 shrink-0" />
        {item.label}
      </button>
    );
  };

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-slate-900 transition-transform lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-blue-600 p-1.5 text-white">
              <Phone className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Voice CRM</p>
              <p className="text-[11px] text-slate-400">AI call center</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:text-white lg:hidden" aria-label="Close menu">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {link({ id: "dashboard", label: "Dashboard", icon: LayoutDashboard })}

          <p className="px-3 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Voice Channel</p>
          {VOICE_ITEMS.map((item) => link(item, true))}

          <p className="px-3 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">CRM</p>
          {link({ id: "customers", label: "Customers", icon: Users })}
          {link({ id: "bookings", label: "Bookings", icon: CalendarCheck })}

          <p className="px-3 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">WhatsApp</p>
          <div className="flex items-center justify-between rounded-lg px-3 py-2 pl-9 text-sm text-slate-500">
            <span className="flex items-center gap-3">
              <MessageCircle className="h-4 w-4" /> WhatsApp
            </span>
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-400">Soon</span>
          </div>

          <div className="pt-5" />
          {link({ id: "reports", label: "Reports", icon: ChartColumn })}
          {link({ id: "settings", label: "Settings", icon: Settings })}
        </nav>

        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span
              className={`h-2 w-2 rounded-full ${
                registration === "registered" ? "bg-emerald-400" : registration === "failed" ? "bg-red-400" : "bg-amber-400"
              }`}
            />
            <span>
              Softphone: {REG_LABEL[registration]}
              {sipMode && <span className="ml-1 uppercase text-slate-500">· {sipMode}</span>}
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}
