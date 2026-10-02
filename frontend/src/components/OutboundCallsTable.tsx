import { formatDuration } from "../lib/format";
import { CallTable, CustomerCell, DateCell, agentLabel, muted, type CallTableProps, type Column } from "./CallTables";
import { OutcomeBadge, StatusBadge } from "./ui";

export function OutboundCallsTable(props: CallTableProps) {
  const columns: Column[] = [
    { label: "Date & Time", render: (c) => <DateCell iso={c.started_at} /> },
    { label: "Customer", render: (c) => <CustomerCell call={c} /> },
    { label: "Phone", render: (c) => c.customer_phone },
    { label: "Brand", render: (c) => muted(c.brand_name) },
    { label: "Called By", render: agentLabel },
    { label: "Purpose", render: (c) => muted(c.purpose) },
    { label: "Duration", render: (c) => <span className="font-mono tabular-nums">{formatDuration(c.duration_seconds)}</span> },
    { label: "Status", render: (c) => <StatusBadge status={c.status} /> },
    { label: "Outcome", render: (c) => <OutcomeBadge outcome={c.outcome} /> },
  ];
  return <CallTable {...props} columns={columns} actionLabel="Redial" emptyText="Dial a number in the softphone to place an outbound call." />;
}
