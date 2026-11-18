"""Dark underground ambience (offline fallback for ElevenLabs music): low detuned pad in D minor,
slow swells, a distant heartbeat-like pulse, airy noise. python drone.py out.wav seconds"""
import sys, wave
import numpy as np
out, secs = sys.argv[1], float(sys.argv[2])
SR = 44100
t = np.arange(int(secs * SR)) / SR
rng = np.random.default_rng(3)
def pad(freqs, amp):
    x = np.zeros_like(t)
    for f in freqs:
        for d in (-0.15, 0.0, 0.17):
            ph = rng.uniform(0, 6.28)
            x += np.sin(2 * np.pi * (f + d) * t + ph) + 0.3 * np.sin(2 * np.pi * 2 * (f + d) * t + ph)
    return x * amp
chord_a = pad([36.71, 73.42, 87.31, 110.0], 0.05)      # D1 D2 F2 A2
chord_b = pad([34.65, 69.30, 87.31, 103.83], 0.05)     # Db-ish tension
swell = 0.5 - 0.5 * np.cos(2 * np.pi * t / 12.0)
mix = chord_a * (1 - swell * 0.6) + chord_b * swell * 0.6
noise = rng.standard_normal(len(t))
k = 400; air = np.convolve(noise, np.ones(k) / k, mode="same") * 0.6
pulse = np.zeros_like(t)
for beat in np.arange(1.0, secs, 1.6):
    for off, a in ((0, 1.0), (0.28, 0.6)):
        i = int((beat + off) * SR); n = int(0.35 * SR)
        if i + n < len(t):
            tt = np.arange(n) / SR
            pulse[i:i + n] += a * np.sin(2 * np.pi * 48 * tt) * np.exp(-tt * 14)
y = mix + air * 0.15 + pulse * 0.25
fade = np.minimum(1, np.minimum(t / 2.0, (secs - t) / 2.5))
y = y * fade
y = y / np.abs(y).max() * 0.7
st = np.stack([y, np.roll(y, 300)], 1)
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print("ok", out)
