#!/usr/bin/env python3
"""Procedural soundtrack for "Ashfall Camp" (24 s, 48 kHz stereo).

0-12 s  : uneasy low drone + gusting wind (and a distant rumble at the 4.4 s flash)
12-20 s : wind settles, campfire crackle takes over (panned right, like the fire)
20-24 s : thunder after the big strike, a calm close sip of tea, then fade out
"""
import os

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000
DUR = 24.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(1234)


def band(x, lo=None, hi=None, order=4):
    if lo and hi:
        sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    elif lo:
        sos = butter(order, lo, btype="high", fs=SR, output="sos")
    else:
        sos = butter(order, hi, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x)


def env(points):
    """Piecewise-linear envelope from (time, value) pairs."""
    ts, vs = zip(*points)
    return np.interp(t, ts, vs)


def slow_noise(rate, seed):
    r = np.random.default_rng(seed)
    k = np.arange(0, DUR + 2, 1.0 / rate)
    v = r.standard_normal(len(k))
    return np.interp(t, k, v)


def smoothstep(a, b, x):
    y = np.clip((x - a) / (b - a), 0, 1)
    return y * y * (3 - 2 * y)


L = np.zeros(N)
R = np.zeros(N)

# ---------------- drone ----------------
drone = np.zeros(N)
for f, a, det in ((36.7, 1.0, 0.13), (55.0, 0.7, 0.21), (73.4, 0.35, 0.17), (77.8, 0.18, 0.11)):
    drone += a * (np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * (f + det) * t + 1.3))
saw = sum(np.sin(2 * np.pi * 55.0 * k * t + k) / k for k in range(1, 18))
drone += 0.35 * band(saw, hi=320) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.09 * t))
# dissonant high whine
whine = (np.sin(2 * np.pi * 587.3 * t) + np.sin(2 * np.pi * 622.3 * t + 0.4)) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.21 * t))
drone_env = env([(0, 0), (1.8, 1), (9, 1), (13, 0.35), (17, 0.12), (20, 0.18), (23.2, 0.08), (24, 0)])
drone = drone / np.max(np.abs(drone)) * 0.30 * drone_env + 0.012 * whine * env([(0, 0), (3, 1), (10, 1), (13, 0), (24, 0)])
L += drone
R += drone

# ---------------- wind ----------------
gust = 0.55 + 0.45 * np.tanh(slow_noise(0.6, 7) * 1.2)
w = rng.standard_normal(N)
windL = band(w, 180, 1100, 2) * 0.7 + band(w, 900, 2400, 2) * 0.25
windR = band(np.roll(w, 3000), 180, 1100, 2) * 0.7 + band(np.roll(w, 3000), 900, 2400, 2) * 0.25
whistle = band(rng.standard_normal(N), 700, 760, 2) * (slow_noise(0.4, 9) > 0.3) * 1.5
wenv = env([(0, 0), (1.5, 1), (10, 1), (14, 0.35), (24, 0.25)]) * gust
L += 0.22 * (windL + 0.4 * whistle) * wenv
R += 0.22 * (windR + 0.4 * band(np.roll(whistle, 9000), hi=2000)) * wenv


# ---------------- thunder ----------------
def thunder(t0, amp, length, seed, crack=True):
    r = np.random.default_rng(seed)
    out = np.zeros(N)
    i0 = int(t0 * SR)
    n = min(int(length * SR), N - i0)
    tt = np.arange(n) / SR
    nz = r.standard_normal(n)
    rumble = band(nz, hi=170, order=4) * 4.0
    swells = sum(np.exp(-((tt - c) / w) ** 2) for c, w in ((0.25, 0.3), (0.9, 0.5), (1.8, 0.6), (2.6, 0.8)))
    e = (1 - np.exp(-tt / 0.05)) * np.exp(-tt / (length * 0.38)) * (0.6 + 0.6 * swells / swells.max())
    sig = rumble * e
    if crack:
        c = band(r.standard_normal(n), 300, 6000, 2) * np.exp(-tt / 0.09) * 1.4
        c += band(r.standard_normal(n), 80, 900, 2) * np.exp(-tt / 0.35) * 1.2
        sig += c
    out[i0:i0 + n] = sig * amp
    return out


th = (thunder(5.6, 0.18, 4.0, 1, crack=False)        # distant, over the city
      + thunder(19.25, 0.30, 3.5, 2, crack=False)    # first flicker
      + thunder(20.72, 0.85, 4.2, 3, crack=True)     # the big strike
      + thunder(22.95, 0.35, 2.0, 4, crack=False))
th *= env([(0, 1), (23.0, 1), (24, 0)])
L += th * 0.9
R += np.roll(th, 220) * 0.9   # slight spread

# ---------------- campfire ----------------
fire_env = smoothstep(11.5, 15.5, t) * env([(0, 1), (23.0, 1), (24, 0.0)])
# low breathing roar of the flames
roar = band(np.cumsum(rng.standard_normal(N)) * 0.02, 40, 350, 2)
roar = roar / np.max(np.abs(roar)) * (0.7 + 0.3 * slow_noise(1.5, 3))
fire = 0.16 * roar
# crackles and pops
crk = np.zeros(N)
times = np.cumsum(rng.exponential(1 / 14.0, 600))
times = times[times < DUR - 0.1]
for tc in times:
    i = int(tc * SR)
    a = min(1.0, rng.pareto(2.2) * 0.25 + 0.05)
    ln = int(SR * rng.uniform(0.002, 0.018))
    burst = rng.standard_normal(ln) * np.exp(-np.arange(ln) / (ln / 4))
    crk[i:i + ln] += burst * a
    if rng.random() < 0.08:   # occasional sharp pop with a tail of sparks
        for k in range(rng.integers(2, 6)):
            j = i + int(SR * rng.uniform(0.01, 0.12))
            ln2 = int(SR * 0.004)
            if j + ln2 < N:
                crk[j:j + ln2] += rng.standard_normal(ln2) * np.exp(-np.arange(ln2) / 40) * a * 0.6
crk = band(crk, 900, 9000, 2) * 0.55 + band(crk, 200, 900, 2) * 0.3
fire = (fire + crk) * fire_env
L += fire * 1.25
R += fire * 1.9

# ---------------- the sip ----------------
sip = np.zeros(N)
s0 = int(21.15 * SR)
n = int(0.42 * SR)
tt = np.arange(n) / SR
slurp_env = smoothstep(0, 0.04, tt) * (1 - smoothstep(0.25, 0.40, tt)) * (0.55 + 0.45 * np.sin(2 * np.pi * 34 * tt) ** 2)
slurp = band(rng.standard_normal(n), 1800, 5200, 2) * slurp_env * 0.55
slurp += band(rng.standard_normal(n), 400, 1200, 2) * slurp_env * 0.25
sip[s0:s0 + n] += slurp
# soft gulp
g0 = int(21.72 * SR)
gn = int(0.16 * SR)
gt = np.arange(gn) / SR
fr = 210 * np.exp(-gt / 0.09) + 95
gulp = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-gt / 0.045) * smoothstep(0, 0.006, gt)
gulp += band(rng.standard_normal(gn), 150, 700, 2) * np.exp(-gt / 0.02) * 0.4
sip[g0:g0 + gn] += gulp * 0.5
# content exhale
e0 = int(22.25 * SR)
en = int(0.9 * SR)
et = np.arange(en) / SR
sip[e0:e0 + en] += band(rng.standard_normal(en), 300, 2500, 2) * np.sin(np.pi * et / 0.9) ** 2 * 0.07
L += sip * 1.7
R += sip * 1.7

# ---------------- master ----------------
mix = np.stack([L, R], 1)
mix = np.tanh(mix * 1.1) / 1.1
mix *= env([(0, 0), (0.6, 1), (23.3, 1), (24, 0)])[:, None]
mix /= np.max(np.abs(mix)) / 0.89
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "soundtrack.wav")
os.makedirs(os.path.dirname(out), exist_ok=True)
wavfile.write(out, SR, (mix * 32767).astype(np.int16))
print("wrote", out)
