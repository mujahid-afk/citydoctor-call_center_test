import { Eye, Phone } from "lucide-react";
import type { ReactNode } from "react";
import type { Call } from "../api";
import { formatDateParts } from "../lib/format";
import { EmptyState, ErrorBanner, TableSkeleton, btnGhost, td, th } from "./ui";

export interface CallTableProps {
  calls: Call[] | null;
  error: string | null;
  onRetry: () => void;
  onOpen: (call: Call) => void;
  onDial: (phone: string) => void;
}

export interface Column {
  label: string;
  render: (call: Call) => ReactNode;
}

export function DateCell({ iso }: { iso: string }) {
  const { date, time } = formatDateParts(iso);
  return (
    <div>
      <p className="font-medium text-slate-900">{date}</p>
      <p className="text-xs text-slate-500">{time}</p>
    </div>
  );
}

export function CustomerCell({ call }: { call: Call }) {
  return call.customer_name ? (
    <span className="font-medium text-slate-900">{call.customer_name}</span>
  ) : (
    <span className="italic text-slate-400">Unknown</span>
  );
}

export const agentLabel = (call: Call) =>
  call.sip_extension ? `Ext. ${call.sip_extension}` : call.elevenlabs_conversation_id ? "ElevenLabs AI" : "—";

export function CallTable({ columns, emptyText, calls, error, onRetry, onOpen, onDial, actionLabel }: CallTableProps & { columns: Column[]; emptyText: string; actionLabel: string }) {
  if (error && !calls) return <div className="p-5"><ErrorBanner message={error} onRetry={onRetry} /></div>;
  if (!calls) return <TableSkeleton cols={columns.length} />;
  if (calls.length === 0) return <EmptyState title="No calls found" description={emptyText} />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((c) => (
              <th key={c.label} className={th}>{c.label}</th>
            ))}
            <th className={th}>Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {calls.map((call) => (
            <tr key={call.id} className="cursor-pointer hover:bg-slate-50" onClick={() => onOpen(call)}>
              {columns.map((c) => (
                <td key={c.label} className={td}>{c.render(call)}</td>
              ))}
              <td className={td}>
                <div className="flex gap-1">
                  <button type="button" className={btnGhost} onClick={(e) => { e.stopPropagation(); onOpen(call); }}>
                    <Eye className="h-3.5 w-3.5" /> View
                  </button>
                  <button type="button" className={btnGhost} onClick={(e) => { e.stopPropagation(); onDial(call.customer_phone); }}>
                    <Phone className="h-3.5 w-3.5" /> {actionLabel}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const muted = (text: string | null | undefined) => text || <span className="text-slate-400">—</span>;

