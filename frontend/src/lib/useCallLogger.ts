// Bridges softphone events to CRM call records (POST/PATCH /api/calls).
// Lives outside webrtc/ so SIP code stays CRM-agnostic.

import { useCallback, useRef, useState } from "react";
import { api, type CallStatus } from "../api";
import type { SipCallEvent } from "../webrtc/SipContext";
import type { SipCall } from "../webrtc/types";

function finalStatus(call: SipCall): CallStatus {
  switch (call.endReason) {
    case "completed":
      return "completed";
    case "rejected":
      return "rejected";
    case "transferred":
      return "transferred";
    case "missed":
    case "busy_rejected":
      return "missed";
    default:
      return call.answeredAt ? "completed" : "failed";
  }
}

const iso = (ms?: number) => (ms ? new Date(ms).toISOString() : undefined);

export function useCallLogger({
  extension,
  mock,
  onChange,
  onError,
}: {
  extension: string;
  mock: boolean;
  onChange: () => void;
  onError: (message: string) => void;
}) {
  // local SIP call id -> promise of CRM call id (so PATCHes wait for the POST)
  const ids = useRef(new Map<string, Promise<number | null>>());
  const [crmIds, setCrmIds] = useState<Record<string, number>>({});

  const create = useCallback(
    (event: SipCallEvent, status: CallStatus, extra: Record<string, unknown> = {}) => {
      const { call, meta } = event;
      const promise = api
        .createCall({
          direction: call.direction,
          customer_phone: call.remoteNumber,
          status,
          customer_name: meta?.customerName ?? call.remoteDisplayName ?? null,
          brand_id: meta?.brandId ?? null,
          brand_name: call.brandLabel ?? null,
          brand_number: call.calledNumber ?? null,
          queue_name: call.queueName ?? null,
          ivr_path: call.ivrPath ?? null,
          queue_entered_at: iso(call.queueEnteredAt),
          sip_call_id: call.sipCallId ?? null,
          sip_headers: call.sipHeaders ?? null,
          sip_extension: extension || null,
          purpose: meta?.purpose ?? null,
          started_at: iso(call.startedAt),
          is_mock: mock,
          ...extra,
        })
        .then((record) => {
          setCrmIds((prev) => ({ ...prev, [call.id]: record.id }));
          onChange();
          return record.id;
        })
        .catch((error: Error) => {
          onError(`Could not log call: ${error.message}`);
          return null;
        });
      ids.current.set(call.id, promise);
      return promise;
    },
    [extension, mock, onChange, onError],
  );

  const patch = useCallback(
    async (call: SipCall, body: Parameters<typeof api.updateCall>[1]) => {
      const id = await ids.current.get(call.id);
      if (!id) return;
      try {
        await api.updateCall(id, body);
        onChange();
      } catch (error) {
        onError(`Could not update call log: ${(error as Error).message}`);
      }
    },
    [onChange, onError],
  );

  const handleEvent = useCallback(
    (event: SipCallEvent) => {
      const { call } = event;
      switch (event.type) {
        case "incoming":
          void create(event, "ringing");
          break;
        case "started":
          if (!ids.current.has(call.id)) void create(event, "calling", { sip_call_id: call.sipCallId ?? null });
          break;
        case "ringing":
          if (call.direction === "outbound") void patch(call, { status: "ringing" });
          break;
        case "answered":
          void patch(call, { status: "answered", answered_at: iso(call.answeredAt) });
          break;
        case "ended":
        case "failed": {
          const status = finalStatus(call);
          const duration = call.answeredAt && call.endedAt ? Math.round((call.endedAt - call.answeredAt) / 1000) : 0;
          const final = {
            status,
            ended_at: iso(call.endedAt),
            duration_seconds: duration,
            ...(call.error ? { notes: call.error } : {}),
          };
          if (ids.current.has(call.id)) void patch(call, final);
          // Calls that never got logged (busy auto-reject, failure before INVITE).
          else void create(event, status, { ...final, answered_at: iso(call.answeredAt) });
          break;
        }
        default:
          break;
      }
    },
    [create, patch],
  );

  return { handleEvent, crmIds };
}
