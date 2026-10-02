import { CircleAlert, CircleCheck, Inbox, LoaderCircle, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import type { CallOutcome, CallStatus, Direction } from "../api";
import { humanize } from "../lib/format";

// ------------------------------------------------------------------ buttons / inputs
export const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";
export const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60";
export const btnGhost =
  "inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500";
export const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20";
export const labelClass = "mb-1.5 block text-xs font-medium text-slate-600";

// ------------------------------------------------------------------ badges
const STATUS_STYLES: Record<CallStatus, string> = {
  ringing: "bg-amber-50 text-amber-700 ring-amber-200",
  calling: "bg-blue-50 text-blue-700 ring-blue-200",
  answered: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  missed: "bg-orange-50 text-orange-700 ring-orange-200",
  rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
  transferred: "bg-violet-50 text-violet-700 ring-violet-200",
};

const OUTCOME_STYLES: Record<CallOutcome, string> = {
  booked: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  inquiry: "bg-sky-50 text-sky-700 ring-sky-200",
  interested: "bg-teal-50 text-teal-700 ring-teal-200",
  not_interested: "bg-slate-100 text-slate-600 ring-slate-200",
  callback: "bg-amber-50 text-amber-700 ring-amber-200",
  transferred: "bg-violet-50 text-violet-700 ring-violet-200",
  completed: "bg-green-50 text-green-700 ring-green-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
};

const badgeBase = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function StatusBadge({ status }: { status: CallStatus }) {
  const live = status === "calling" || status === "ringing" || status === "answered";
  return (
    <span className={`${badgeBase} ${STATUS_STYLES[status]}`}>
      {live && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {humanize(status)}
    </span>
  );
}

export function OutcomeBadge({ outcome }: { outcome: CallOutcome | null }) {
  if (!outcome) return <span className="text-slate-400">—</span>;
  return <span className={`${badgeBase} ${OUTCOME_STYLES[outcome]}`}>{humanize(outcome)}</span>;
}

export function DirectionBadge({ direction }: { direction: Direction }) {
  return (
    <span
      className={`${badgeBase} ${
        direction === "inbound" ? "bg-cyan-50 text-cyan-700 ring-cyan-200" : "bg-blue-50 text-blue-700 ring-blue-200"
      }`}
    >
      {humanize(direction)}
    </span>
  );
}

export function MockBadge() {
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
      mock
    </span>
  );
}

// ------------------------------------------------------------------ feedback
export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <LoaderCircle className={`animate-spin ${className}`} aria-hidden />;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-400">
        <Inbox className="h-6 w-6" />
      </div>
      <p className="text-sm font-medium text-slate-900">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 8 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-slate-100">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 px-5 py-4">
          {Array.from({ length: cols }).map((__, c) => (
            <div key={c} className="h-3 flex-1 animate-pulse rounded bg-slate-100" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="flex-1">{message}</p>
      {onRetry && (
        <button type="button" className="font-medium underline" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ layout
export function Card({ children, className = "", id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`scroll-mt-20 rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  icon,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        {icon && <div className="rounded-lg bg-blue-50 p-2 text-blue-600">{icon}</div>}
        <div>
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export const th = "whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";
export const td = "whitespace-nowrap px-4 py-3 text-sm text-slate-700";

// ------------------------------------------------------------------ modal
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "xl";
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  const width = size === "xl" ? "max-w-4xl" : size === "lg" ? "max-w-2xl" : "max-w-lg";
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div
        className={`relative flex max-h-[92vh] w-full ${width} flex-col overflow-hidden rounded-t-2xl bg-white shadow-xl sm:rounded-2xl`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
            {subtitle && <div className="mt-0.5 text-sm text-slate-500">{subtitle}</div>}
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-slate-50 px-6 py-3">{footer}</div>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ toast
export interface ToastMessage {
  id: number;
  kind: "success" | "error" | "info";
  text: string;
}

export function Toasts({ toasts, onDismiss }: { toasts: ToastMessage[]; onDismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg ${
            toast.kind === "error"
              ? "border-red-200 bg-white text-red-700"
              : toast.kind === "success"
                ? "border-emerald-200 bg-white text-emerald-700"
                : "border-slate-200 bg-white text-slate-700"
          }`}
        >
          {toast.kind === "error" ? <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" /> : <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" />}
          <p className="flex-1">{toast.text}</p>
          <button type="button" onClick={() => onDismiss(toast.id)} className="text-slate-400 hover:text-slate-600" aria-label="Dismiss">
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
