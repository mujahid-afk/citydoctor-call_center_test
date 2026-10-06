import { formatDuration } from "../lib/format";
import { CallTable, CustomerCell, DateCell, agentLabel, muted, type CallTableProps, type Column } from "./CallTables";
import { OutcomeBadge, StatusBadge } from "./ui";

export function InboundCallsTable(props: CallTableProps) {
  const columns: Column[] = [
    { label: "Date & Time", render: (c) => <DateCell iso={c.started_at} /> },
    { label: "Customer", render: (c) => <CustomerCell call={c} /> },
    { label: "Phone", render: (c) => c.customer_phone },
    { label: "Brand", render: (c) => muted(c.brand_name) },
    { label: "Number", render: (c) => muted(c.brand_number) },
    {
      label: "Queue",
      render: (c) =>
        c.queue_name ? (
          <div>
            <p className="text-slate-900">{c.queue_name}</p>
            {c.wait_seconds !== null && <p className="text-xs text-slate-500">waited {formatDuration(c.wait_seconds)}</p>}
          </div>
        ) : (
          muted(null)
        ),
    },
    { label: "Extension / Agent", render: agentLabel },
    { label: "Duration", render: (c) => <span className="font-mono tabular-nums">{formatDuration(c.duration_seconds)}</span> },
    { label: "Status", render: (c) => <StatusBadge status={c.status} /> },
    { label: "Outcome", render: (c) => <OutcomeBadge outcome={c.outcome} /> },
    { label: "Booking", render: (c) => (c.booking_reference ? <span className="font-medium text-blue-700">{c.booking_reference}</span> : muted(null)) },
  ];
  return <CallTable {...props} columns={columns} actionLabel="Call back" emptyText="Inbound calls appear here when the softphone receives them." />;
}

