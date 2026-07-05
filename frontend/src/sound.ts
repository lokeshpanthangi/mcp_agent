// Tiny synthesized sound effects via the Web Audio API — no asset files.
// Sounds only play after a user gesture (send click), so autoplay policies are fine.

const MUTE_KEY = "mcp_agent_muted";

let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  try {
    if (!ctx) {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

export function isMuted(): boolean {
  return localStorage.getItem(MUTE_KEY) === "1";
}
export function setMuted(muted: boolean) {
  localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
}

function tone(
  freq: number,
  startAt: number,
  duration: number,
  peak = 0.08,
  type: OscillatorType = "sine",
) {
  const c = audio();
  if (!c) return;
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  osc.connect(gain);
  gain.connect(c.destination);
  const t = c.currentTime + startAt;
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(peak, t + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
  osc.start(t);
  osc.stop(t + duration + 0.03);
}

/** Soft ascending shimmer when a response finishes. */
export function playComplete() {
  if (isMuted()) return;
  tone(587.33, 0, 0.45, 0.06); // D5
  tone(880.0, 0.07, 0.5, 0.06); // A5
  tone(1174.66, 0.14, 0.6, 0.05); // D6
  tone(1567.98, 0.22, 0.7, 0.03, "triangle"); // G6 sparkle
}

/** Barely-there tick when the user sends a message. */
export function playSend() {
  if (isMuted()) return;
  tone(392.0, 0, 0.12, 0.035, "triangle");
}
