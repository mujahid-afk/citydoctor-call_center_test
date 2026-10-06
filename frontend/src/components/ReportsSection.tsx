import { ChartColumn } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type BreakdownBy, type BreakdownRow, type CallFilters } from "../api";
import { formatDuration } from "../lib/format";
import { Card, CardHeader, EmptyState, ErrorBanner, TableSkeleton, td, th } from "./ui";

interface Column {
  label: string;
  title?: string;
  render: (row: BreakdownRow) => React.ReactNode;
}

const num = (value: number) => <span className="tabular-nums">{value}</span>;
const time = (value: number) => <span className="font-mono tabular-nums">{value ? formatDuration(value) : "—"}</span>;
const rate = (row: BreakdownRow) => (
  <span className={`tabular-nums ${row.answer_rate < 80 && row.total_calls ? "text-orange-600" : ""}`}>{row.answer_rate}%</span>
);

const QUEUE_COLUMNS: Column[] = [
  { label: "Queue", render: (r) => <span className="font-medium text-slate-900">{r.name}</span> },
  { label: "Brand", render: (r) => r.brand_name ?? <span className="text-slate-400">—</span> },
  { label: "Department", render: (r) => r.department ?? <span className="text-slate-400">—</span> },
  { label: "Calls", render: (r) => num(r.total_calls) },
  { label: "Answered", render: (r) => num(r.answered) },
  { label: "Missed", title: "Missed or rejected (caller abandoned / not answered)", render: (r) => num(r.missed) },
  { label: "Answer rate", title: "Answered / finished calls", render: rate },
  { label: "Avg wait", title: "Average wait of answered calls", render: (r) => time(r.average_wait_seconds) },
  { label: "Max wait", title: "Longest wait, including abandoned calls", render: (r) => time(r.max_wait_seconds) },
  { label: "Avg talk", render: (r) => time(r.average_duration_seconds) },
  { label: "Bookings", render: (r) => num(r.bookings) },
];

const BRAND_COLUMNS: Column[] = [
  { label: "Brand", render: (r) => <span className="font-medium text-slate-900">{r.name}</span> },
  { label: "Calls", render: (r) => num(r.total_calls) },
  { label: "Inbound", render: (r) => num(r.inbound_calls) },
  { label: "Outbound", render: (r) => num(r.outbound_calls) },
  { label: "Answered", render: (r) => num(r.answered) },
  { label: "Missed", render: (r) => num(r.missed) },
  { label: "Failed", render: (r) => num(r.failed) },
  { label: "Answer rate", title: "Answered / finished calls", render: rate },
  { label: "Avg wait", title: "Average wait of answered inbound calls", render: (r) => time(r.average_wait_seconds) },
  { label: "Avg talk", render: (r) => time(r.average_duration_seconds) },
  { label: "Bookings", render: (r) => num(r.bookings) },
];

/** Per-queue / per-brand report for the current filters. Clicking a row filters the dashboard by it. */
export function ReportsSection({
  filters,
  reloadKey,
  onPick,
}: {
  filters: CallFilters;
  /** Changes whenever the dashboard reloads (polling or a call event). */
  reloadKey: unknown;
  onPick: (by: BreakdownBy, id: number) => void;
}) {
  const [by, setBy] = useState<BreakdownBy>("queue");
  const [rows, setRows] = useState<BreakdownRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const filtersKey = JSON.stringify(filters);

  useEffect(() => {
    let cancelled = false;
    api
      .breakdown(by, JSON.parse(filtersKey) as CallFilters)
      .then((r) => !cancelled && (setRows(r), setError(null)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [by, filtersKey, reloadKey]);

  const columns = by === "queue" ? QUEUE_COLUMNS : BRAND_COLUMNS;
  const tab = (value: BreakdownBy, label: string) => (
    <button
      type="button"
      onClick={() => {
        setBy(value);
        setRows(null);
      }}
      className={`rounded-md px-3 py-1.5 text-xs font-medium ${by === value ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
    >
      {label}
    </button>
  );

  return (
    <Card id="reports">
      <CardHeader
        icon={<ChartColumn className="h-4 w-4" />}
        title="Reports"
        subtitle={by === "queue" ? "Inbound calls per queue · current filters" : "Calls per brand · current filters"}
        actions={
          <div className="flex rounded-lg bg-slate-100 p-0.5">
            {tab("queue", "By queue")}
            {tab("brand", "By brand")}
          </div>
        }
      />
      {error && !rows ? (
        <div className="p-5"><ErrorBanner message={error} /></div>
      ) : !rows ? (
        <TableSkeleton rows={3} cols={columns.length} />
      ) : rows.length === 0 ? (
        <EmptyState title="No calls for these filters" description="Queues appear here once FreePBX sends X-Queue on inbound calls." />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50">
              <tr>
                {columns.map((c) => (
                  <th key={c.label} className={th} title={c.title}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => (
                <tr
                  key={`${row.id ?? "none"}-${row.name}`}
                  className={row.id ? "cursor-pointer hover:bg-slate-50" : ""}
                  onClick={() => row.id && onPick(by, row.id)}
                  title={row.id ? `Show only ${row.name}` : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.label} className={td}>{c.render(row)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
