// Resolve the brand / queue of a live call from what FreePBX sent (same rules as the backend).

import type { Brand, Queue } from "../api";
import type { SipCall } from "../webrtc/types";

/** Loose label comparison: "City Doctor", "CityDoctor" and "city-doctor" are the same. */
export const labelKey = (value?: string | null) => (value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");

export function findQueue(queues: Queue[], name?: string | null): Queue | undefined {
  const key = labelKey(name);
  return key ? queues.find((q) => labelKey(q.name) === key) : undefined;
}

/** The number without its international or trunk prefix: +97142000104 and 042000104 -> 42000104. */
export function nationalNumber(number?: string | null, countryCode = "971"): string {
  let digits = (number ?? "").replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2);
  else if (digits.startsWith("0")) return digits.slice(1);
  return digits.startsWith(countryCode) && digits.length > countryCode.length + 6 ? digits.slice(countryCode.length) : digits;
}

/** False for withheld caller IDs ("anonymous"), which cannot be called back. */
export const isDialable = (phone?: string | null) => /\d/.test(phone ?? "");

export function brandByNumber(brands: Brand[], number?: string | null): Brand | undefined {
  const did = nationalNumber(number);
  if (!did) return undefined;
  return brands.find((b) => nationalNumber(b.phone_number) === did);
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
