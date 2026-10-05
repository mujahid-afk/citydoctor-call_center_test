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
let active: { kind: ToneKind; timer: number; nodes: AudioNode[] } | null = null;

function audioContext(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  ctx ??= new AudioContext();
  // Resume may be refused before any user gesture (autoplay policy); ignore.
  if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
  return ctx;
}

function scheduleCycle(ac: AudioContext, kind: ToneKind, start: number, nodes: AudioNode[]): void {
  const pattern = PATTERNS[kind];
  for (const burst of pattern.bursts) {
    const t0 = start + burst.at;
    const t1 = t0 + burst.duration;
    const gain = ac.createGain();
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(pattern.gain, t0 + 0.01);
    gain.gain.setValueAtTime(pattern.gain, t1 - 0.01);
    gain.gain.linearRampToValueAtTime(0, t1);
    gain.connect(ac.destination);
    nodes.push(gain);
    for (const freq of burst.freqs) {
      const osc = ac.createOscillator();
      osc.frequency.value = freq;
      osc.connect(gain);
      osc.start(t0);
      osc.stop(t1);
      nodes.push(osc);
    }
  }
}

export function startTone(kind: ToneKind): void {
  if (active?.kind === kind) return;
  stopTone();
  const ac = audioContext();
  if (!ac) return;
  const nodes: AudioNode[] = [];
  const cycle = PATTERNS[kind].cycle;
  let next = ac.currentTime + 0.05;
  const tick = () => {
    // Keep one cycle scheduled ahead.
    while (next < ac.currentTime + cycle) {
      scheduleCycle(ac, kind, next, nodes);
      next += cycle;
    }
    // Drop references to nodes that have finished.
    if (nodes.length > 200) nodes.splice(0, nodes.length - 100);
  };
  tick();
  active = { kind, timer: window.setInterval(tick, 500), nodes };
}

export function stopTone(): void {
  if (!active) return;
  window.clearInterval(active.timer);
  for (const node of active.nodes) {
    try {
      node.disconnect();
    } catch {
      // already disconnected
    }
  }
  active = null;
}

/** Call from a user gesture (e.g. the Call button) so later tones are allowed to play. */
export function unlockTones(): void {
  audioContext();
}
