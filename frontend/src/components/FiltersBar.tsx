import { Search, X } from "lucide-react";
import { CALL_OUTCOMES, CALL_STATUSES, type Brand, type CallOutcome, type CallStatus, type Direction, type Queue } from "../api";
import { humanize } from "../lib/format";
import { btnGhost, inputClass } from "./ui";

export interface FilterState {
  search: string;
  direction: Direction | "";
  brandId: number | "";
  queueId: number | "";
  status: CallStatus | "";
  outcome: CallOutcome | "";
  dateFrom: string; // YYYY-MM-DD (local)
  dateTo: string;
}

export const EMPTY_FILTERS: FilterState = { search: "", direction: "", brandId: "", queueId: "", status: "", outcome: "", dateFrom: "", dateTo: "" };

export function FiltersBar({
  value,
  onChange,
  brands,
  queues,
}: {
  value: FilterState;
  onChange: (next: FilterState) => void;
  brands: Brand[];
  queues: Queue[];
}) {
  const set = <K extends keyof FilterState>(key: K, v: FilterState[K]) => onChange({ ...value, [key]: v });
  const brandQueues = value.brandId ? queues.filter((q) => q.brand_id === value.brandId) : queues;
  const setBrand = (brandId: number | "") =>
    // Drop a queue filter that belongs to another brand.
    onChange({ ...value, brandId, queueId: brandId && queues.find((q) => q.id === value.queueId)?.brand_id !== brandId ? "" : value.queueId });
  const active = JSON.stringify(value) !== JSON.stringify(EMPTY_FILTERS);
  const select = `${inputClass} w-auto min-w-[8.5rem]`;
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm lg:flex-row lg:flex-wrap lg:items-center">
      <div className="relative min-w-[14rem] flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input className={`${inputClass} pl-9`} placeholder="Search customer name or phone" value={value.search} onChange={(e) => set("search", e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <select className={select} value={value.direction} onChange={(e) => set("direction", e.target.value as FilterState["direction"])} aria-label="Direction">
          <option value="">Inbound & Outbound</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
        </select>
        <select className={select} value={value.brandId} onChange={(e) => setBrand(e.target.value ? Number(e.target.value) : "")} aria-label="Brand">
          <option value="">All brands</option>
          {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <select className={select} value={value.queueId} onChange={(e) => set("queueId", e.target.value ? Number(e.target.value) : "")} aria-label="Queue">
          <option value="">All queues</option>
          {brandQueues.map((q) => <option key={q.id} value={q.id}>{q.name}{q.active ? "" : " (inactive)"}</option>)}
        </select>
        <select className={select} value={value.status} onChange={(e) => set("status", e.target.value as FilterState["status"])} aria-label="Status">
          <option value="">All statuses</option>
          {CALL_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
        </select>
        <select className={select} value={value.outcome} onChange={(e) => set("outcome", e.target.value as FilterState["outcome"])} aria-label="Outcome">
          <option value="">All outcomes</option>
          {CALL_OUTCOMES.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}
        </select>
        <input type="date" className={`${inputClass} w-auto`} value={value.dateFrom} onChange={(e) => set("dateFrom", e.target.value)} aria-label="From date" title="From date" />
        <input type="date" className={`${inputClass} w-auto`} value={value.dateTo} onChange={(e) => set("dateTo", e.target.value)} aria-label="To date" title="To date" />
        {active && (
          <button type="button" className={btnGhost} onClick={() => onChange(EMPTY_FILTERS)}>
            <X className="h-3.5 w-3.5" /> Clear
          </button>
        )}
      </div>
    </div>
  );
}
