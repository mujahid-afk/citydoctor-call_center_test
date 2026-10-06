// Typed client for the FastAPI CRM backend (REST only - no audio ever goes here).

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export type Direction = "inbound" | "outbound";
export type CallStatus = "ringing" | "calling" | "answered" | "completed" | "missed" | "rejected" | "failed" | "transferred";
export type CallOutcome =
  | "booked" | "inquiry" | "interested" | "not_interested" | "callback" | "transferred" | "completed" | "failed";

export const CALL_STATUSES: CallStatus[] = ["ringing", "calling", "answered", "completed", "missed", "rejected", "failed", "transferred"];
export const CALL_OUTCOMES: CallOutcome[] = [
  "booked", "inquiry", "interested", "not_interested", "callback", "transferred", "completed", "failed",
];
export const PURPOSES = [
  "Appointment Reminder", "Follow Up", "Lead Qualification", "Booking Follow Up", "General Inquiry", "Campaign", "Custom",
] as const;

export interface Brand {
  id: number;
  name: string;
  phone_number: string;
  elevenlabs_agent_id: string | null;
  active: boolean;
  created_at: string;
}

export interface Queue {
  id: number;
  /** As FreePBX sends it in X-Queue, e.g. "CD-Booking". */
  name: string;
  brand_id: number | null;
  brand_name: string | null;
  department: string | null;
  number: string | null;
  active: boolean;
  created_at: string;
}

export interface Customer {
  id: number;
  name: string;
  phone: string;
  email: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Call {
  id: number;
  direction: Direction;
  customer_id: number | null;
  customer_name: string | null;
  customer_phone: string;
  brand_id: number | null;
  brand_name: string | null;
  brand_number: string | null;
  queue_id: number | null;
  queue_name: string | null;
  ivr_path: string | null;
  queue_entered_at: string | null;
  /** Inbound: seconds the caller waited (queue + ringing) until answer or hang-up. */
  wait_seconds: number | null;
  sip_call_id: string | null;
  sip_extension: string | null;
  elevenlabs_conversation_id: string | null;
  status: CallStatus;
  outcome: CallOutcome | null;
  purpose: string | null;
  started_at: string;
  answered_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  summary: string | null;
  transcript: string | null;
  recording_url: string | null;
  booking_id: number | null;
  booking_reference: string | null;
  notes: string | null;
  is_mock: boolean;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total_calls: number;
  inbound_calls: number;
  outbound_calls: number;
  answered: number;
  missed: number;
  failed: number;
  in_progress: number;
  bookings: number;
  average_duration_seconds: number;
  /** Average wait of answered inbound calls. */
  average_wait_seconds: number;
}

export type BreakdownBy = "queue" | "brand";

export interface BreakdownRow {
  id: number | null;
  name: string;
  brand_name: string | null;
  department: string | null;
  total_calls: number;
  inbound_calls: number;
  outbound_calls: number;
  answered: number;
  missed: number;
  failed: number;
  bookings: number;
  answer_rate: number;
  average_wait_seconds: number;
  max_wait_seconds: number;
  average_duration_seconds: number;
}

export interface Booking {
  id: number;
  reference: string;
  customer_id: number;
  customer_name: string | null;
  call_id: number | null;
  service: string;
  appointment_date: string;
  appointment_time: string;
  status: "confirmed" | "rescheduled" | "cancelled" | "completed";
  notes: string | null;
  created_at: string;
}

export interface CustomerLookup {
  customer: Customer;
  recent_calls: Call[];
  bookings: Booking[];
}

export interface CallFilters {
  direction?: Direction | "";
  search?: string;
  brand_id?: number | "";
  queue_id?: number | "";
  status?: CallStatus | "";
  outcome?: CallOutcome | "";
  date_from?: string;
  date_to?: string;
}

export interface CallCreate {
  direction: Direction;
  customer_phone: string;
  status: CallStatus;
  customer_name?: string | null;
  brand_id?: number | null;
  brand_name?: string | null;
  brand_number?: string | null;
  queue_name?: string | null;
  ivr_path?: string | null;
  queue_entered_at?: string;
  sip_call_id?: string | null;
  sip_extension?: string | null;
  purpose?: string | null;
  notes?: string | null;
  started_at?: string;
  is_mock?: boolean;
}

export type CallUpdate = Partial<
  Pick<Call, "status" | "outcome" | "notes" | "purpose" | "customer_id" | "brand_id" | "sip_call_id" | "answered_at" | "ended_at" | "duration_seconds" | "booking_id">
>;

export interface RandomCaller {
  customer_phone: string;
  customer_name: string | null;
  brand_id: number | null;
  brand_name: string | null;
  brand_number: string | null;
  queue_name: string | null;
  ivr_path: string | null;
  /** How long the simulated caller has already waited in the queue. */
  wait_seconds: number;
}

export interface AISummary {
  summary: string;
  suggested_outcome: CallOutcome | null;
  next_action: string;
  call: Call;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string };
          const field = item.loc?.slice(1).join(".");
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    throw new ApiError("Cannot reach the CRM backend. Is FastAPI running on port 8000?", 0);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(body, `Request failed (${response.status})`), response.status);
  return body as T;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string; database: string; app_env: string }>("/api/health"),
  stats: (filters: CallFilters = {}) => request<Stats>(`/api/stats${query({ ...filters, direction: "" })}`),
  breakdown: (by: BreakdownBy, filters: CallFilters = {}) =>
    request<BreakdownRow[]>(`/api/stats/breakdown${query({ ...filters, by })}`),
  brands: () => request<Brand[]>("/api/brands"),
  queues: () => request<Queue[]>("/api/queues"),

  customers: (search?: string) => request<Customer[]>(`/api/customers${query({ search })}`),
  customerByPhone: async (phone: string): Promise<CustomerLookup | null> => {
    try {
      return await request<CustomerLookup>(`/api/customers/by-phone/${encodeURIComponent(phone)}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  createCustomer: (input: { name: string; phone: string; email?: string | null; notes?: string | null }) =>
    request<Customer>("/api/customers", json("POST", input)),
  updateCustomer: (id: number, patch: Partial<Pick<Customer, "name" | "phone" | "email" | "notes">>) =>
    request<Customer>(`/api/customers/${id}`, json("PATCH", patch)),

  calls: (filters: CallFilters = {}, limit = 200) => request<Call[]>(`/api/calls${query({ ...filters, limit })}`),
  call: (id: number) => request<Call>(`/api/calls/${id}`),
  createCall: (input: CallCreate) => request<Call>("/api/calls", json("POST", input)),
  updateCall: (id: number, patch: CallUpdate) => request<Call>(`/api/calls/${id}`, json("PATCH", patch)),
  saveOutcome: (id: number, outcome: CallOutcome, notes?: string | null) =>
    request<Call>(`/api/calls/${id}/outcome`, json("POST", { outcome, notes })),

  bookings: () => request<Booking[]>("/api/bookings"),
  availability: (date: string, service?: string) => request<string[]>(`/api/availability${query({ date, service })}`),
  createBooking: (input: { customer_id: number; call_id?: number | null; service: string; appointment_date: string; appointment_time: string; notes?: string | null }) =>
    request<Booking>("/api/bookings", json("POST", input)),
  updateBooking: (id: number, patch: Partial<Pick<Booking, "status" | "appointment_date" | "appointment_time" | "notes" | "service">>) =>
    request<Booking>(`/api/bookings/${id}`, json("PUT", patch)),

  aiStatus: () => request<{ enabled: boolean; model: string | null }>("/api/ai/status"),
  aiSummary: (id: number, notes?: string | null) =>
    request<AISummary>(`/api/calls/${id}/ai-summary`, json("POST", { notes: notes ?? null })),

  randomCaller: () => request<RandomCaller>("/api/testing/random-caller"),
};
