// Resolve the brand / queue of a live call from what FreePBX sent (same rules as the backend).

import type { Brand, Queue } from "../api";
import type { SipCall } from "../webrtc/types";

/** Loose label comparison: "City Doctor", "CityDoctor" and "city-doctor" are the same. */
export const labelKey = (value?: string | null) => (value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");

export function findQueue(queues: Queue[], name?: string | null): Queue | undefined {
  const key = labelKey(name);
  return key ? queues.find((q) => labelKey(q.name) === key) : undefined;
}

export function brandByNumber(brands: Brand[], number?: string | null): Brand | undefined {
  const digits = (number ?? "").replace(/\D/g, "").slice(-9);
  if (!digits) return undefined;
  return brands.find((b) => b.phone_number.replace(/\D/g, "").slice(-9) === digits);
}

/** X-Brand label > the queue's brand > called DID. */
export function brandForCall(
  brands: Brand[],
  queues: Queue[],
  call: Pick<SipCall, "brandLabel" | "queueName" | "calledNumber">,
): Brand | undefined {
  const key = labelKey(call.brandLabel);
  const byLabel = key ? brands.find((b) => labelKey(b.name) === key) : undefined;
  const queueBrandId = findQueue(queues, call.queueName)?.brand_id;
  return byLabel ?? brands.find((b) => b.id === queueBrandId) ?? brandByNumber(brands, call.calledNumber);
}
