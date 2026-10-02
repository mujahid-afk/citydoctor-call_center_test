export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateParts(iso: string): { date: string; time: string } {
  const value = new Date(iso);
  return {
    date: value.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }),
    time: value.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
  };
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function timeAgo(date: Date | null): string {
  if (!date) return "never";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}

/** Start of a local calendar day ("YYYY-MM-DD") as an ISO string. */
export function startOfDayIso(day: string): string {
  return new Date(`${day}T00:00:00`).toISOString();
}

export function endOfDayIso(day: string): string {
  return new Date(`${day}T23:59:59.999`).toISOString();
}

export function localDateInput(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
