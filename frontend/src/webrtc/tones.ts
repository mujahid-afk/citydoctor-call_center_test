// Locally generated call tones (Web Audio, no audio files).
//
// - Ringback: played for outbound calls while ringing, unless the PBX sends its
//   own ringback as early media (183). UAE/GCC cadence: 400 Hz, 0.4 on, 0.2 off,
//   0.4 on, 2.0 off.
// - Ringtone: played for incoming calls until answered/rejected.

type ToneKind = "ringback" | "ringtone";

interface Burst {
  at: number; // seconds from cycle start
  duration: number;
  freqs: number[];
}

const PATTERNS: Record<ToneKind, { cycle: number; gain: number; bursts: Burst[] }> = {
  ringback: {
    cycle: 3.0,
    gain: 0.08,
    bursts: [
      { at: 0, duration: 0.4, freqs: [400, 450] },
      { at: 0.6, duration: 0.4, freqs: [400, 450] },
    ],
  },
  ringtone: {
    cycle: 3.0,
    gain: 0.12,
    bursts: [
      { at: 0, duration: 0.25, freqs: [880, 1320] },
      { at: 0.3, duration: 0.25, freqs: [660, 990] },
      { at: 0.6, duration: 0.25, freqs: [880, 1320] },
      { at: 0.9, duration: 0.25, freqs: [660, 990] },
    ],
  },
};

let ctx: AudioContext | null = null;
let active: { kind: ToneKind; source: AudioBufferSourceNode } | null = null;
const buffers: Partial<Record<ToneKind, AudioBuffer>> = {};

function audioContext(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  ctx ??= new AudioContext();
  // Resume may be refused before any user gesture (autoplay policy); ignore.
  if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
  return ctx;
}

/**
 * One cycle of the tone, rendered once. It is played as a looping buffer so no timer is
 * involved: background tabs throttle timers (to once a minute), which cut timer-driven tones off.
 */
function renderCycle(ac: AudioContext, kind: ToneKind): AudioBuffer {
  const { cycle, gain, bursts } = PATTERNS[kind];
  const rate = ac.sampleRate;
  const buffer = ac.createBuffer(1, Math.round(cycle * rate), rate);
  const data = buffer.getChannelData(0);
  const ramp = 0.01 * rate; // 10 ms fade in/out, no clicks
  for (const burst of bursts) {
    const start = Math.round(burst.at * rate);
    const length = Math.round(burst.duration * rate);
    for (let i = 0; i < length; i++) {
      let sample = 0;
      for (const freq of burst.freqs) sample += Math.sin((2 * Math.PI * freq * i) / rate);
      data[start + i] += gain * Math.min(1, i / ramp, (length - i) / ramp) * sample;
    }
  }
  return buffer;
}

export function startTone(kind: ToneKind): void {
  if (active?.kind === kind) return;
  stopTone();
  const ac = audioContext();
  if (!ac) return;
  const source = ac.createBufferSource();
  source.buffer = buffers[kind] ??= renderCycle(ac, kind);
  source.loop = true;
  source.connect(ac.destination);
  source.start(ac.currentTime + 0.05);
  console.info(`[softphone] ${kind} tone on (audio ${ac.state})`);
  active = { kind, source };
}

export function stopTone(): void {
  if (!active) return;
  try {
    active.source.stop();
  } catch {
    // not started yet
  }
  active.source.disconnect();
  active = null;
}

/**
 * Call from a user gesture (click / key press): browsers mute a page until the user has
 * interacted with it. Resolves to true once tones can be heard.
 */
export async function unlockTones(): Promise<boolean> {
  const ac = audioContext();
  if (!ac) return false;
  if (ac.state === "suspended") await ac.resume().catch(() => undefined);
  return ac.state === "running";
}
