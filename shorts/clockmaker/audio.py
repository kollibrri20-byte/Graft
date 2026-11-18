"""Soundtrack for The Clockmaker: narration placed on the storyboard slots, procedural dark-ambient score,
procedural clock ticks / heartbeat / footsteps / wind / thuds, plus ElevenLabs effects (bell, crack, dust, laughter).
-> mix.wav (48 kHz stereo) and words.json (approximate word timings for captions)."""
import json
import os
import re
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
DUR = 94.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)

L = json.load(open(os.path.join(HERE, "lines_raw.json")))
S = [0.0] + [round(l["at"] - 0.25, 2) for l in L[1:]] + [DUR]
AT = [l["at"] for l in L]
TICK_T = AT[26] + 0.85
DIS_T0 = AT[8] + 0.05


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def band(x, lo=None, hi=None, order=4):
    if lo and hi:
        sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    elif lo:
        sos = butter(order, lo, btype="high", fs=SR, output="sos")
    else:
        sos = butter(order, hi, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0)


def env(points, tt=None):
    tt = t if tt is None else tt
    ts, vs = zip(*points)
    return np.interp(tt, ts, vs)


def put(buf, x, at, gain=1.0, pan=0.0):
    if x.ndim == 1:
        x = np.column_stack([x * (1 - max(0, pan)), x * (1 + min(0, pan))])
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    if i < 0:
        x = x[-i:]
        i = 0
    buf[i:j] += x[: j - i] * gain


def movavg(x, n):
    c = np.cumsum(np.concatenate([np.zeros(n), x, np.zeros(n)]))
    y = (c[n:] - c[:-n]) / n
    return y[n // 2: n // 2 + len(x)]


def db(x):
    return 10 ** (x / 20)


# simple stereo reverb (decaying noise impulse)
def reverb(x, secs=2.5, wet=0.35, seed=1):
    r = np.random.default_rng(seed)
    n = int(SR * secs)
    tt = np.arange(n) / SR
    ir = r.standard_normal((n, 2)) * np.exp(-tt * 4.5 / secs)[:, None]
    ir = band(ir, 200, 7000, 2)
    ir /= np.abs(ir).sum(0) ** 0.5 * 8
    y = np.column_stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)])
    return x * (1 - wet) + y * wet * 3


# ------------------------------------------------------------------ narration
voice_raw = load(os.path.join(HERE, "voice_raw.mp3"))
voice = np.zeros((N, 2))
words = []
for l in L:
    a, b = int((l["s"] - 0.04) * SR), int((l["e"] + 0.12) * SR)
    seg = voice_raw[max(0, a):b].copy()
    f = int(0.02 * SR)
    seg[:f] *= np.linspace(0, 1, f)[:, None]
    seg[-f * 3:] *= np.linspace(1, 0, f * 3)[:, None]
    put(voice, seg, l["at"] - 0.04)
    # approximate word timings (proportional to letters)
    ws = l["text"].replace("…", " ").replace("«", "").replace("»", "").split()
    ws = [w for w in ws if re.sub(r"[^\w]", "", w)]
    lens = np.array([len(re.sub(r"[^\w]", "", w)) + 1.5 for w in ws], float)
    dur = l["e"] - l["s"]
    edges = np.concatenate([[0], np.cumsum(lens)]) / lens.sum() * dur
    for k, w in enumerate(ws):
        words.append({"w": w.strip(",.:;—"), "raw": w, "s": round(l["at"] + edges[k], 3), "e": round(l["at"] + edges[k + 1], 3), "line": l["i"]})
json.dump(words, open(os.path.join(HERE, "words.json"), "w"), ensure_ascii=False, indent=0)
voice = band(voice, 70, None, 2) * 1.0

# ------------------------------------------------------------------ procedural sounds
def tick(kind="small", seed=0):
    r = np.random.default_rng(seed)
    n = int(SR * (0.25 if kind != "big" else 4.0))
    tt = np.arange(n) / SR
    click = r.standard_normal(n) * np.exp(-tt * (900 if kind != "big" else 300))
    click = band(click, 1500 if kind == "small" else 600, 9000, 2)
    f0 = {"small": 3100, "mid": 2200, "deep": 1200, "big": 880}[kind]
    ring = np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * (60 if kind != "big" else 1.2)) * 0.3
    if kind == "big":
        ring += 0.25 * np.sin(2 * np.pi * f0 * 1.5 * tt) * np.exp(-tt * 1.6) + 0.2 * np.sin(2 * np.pi * f0 * 0.5 * tt) * np.exp(-tt * 1.0)
        body = np.sin(2 * np.pi * 70 * tt) * np.exp(-tt * 9) * 0.8
        ring += body
    x = click + ring
    return x / np.abs(x).max()


def heartbeat():
    n = int(SR * 0.9)
    tt = np.arange(n) / SR
    def thump(t0, a):
        tt2 = np.clip(tt - t0, 0, None)
        return a * np.sin(2 * np.pi * (48 + 30 * np.exp(-tt2 * 20)) * tt2) * np.exp(-tt2 * 14) * (tt >= t0)
    x = thump(0, 1.0) + thump(0.24, 0.7)
    return band(x, None, 180, 2)


def thud(f=60, dec=8, noise=0.4, seed=0):
    n = int(SR * 1.2)
    tt = np.arange(n) / SR
    r = np.random.default_rng(seed)
    x = np.sin(2 * np.pi * (f + 60 * np.exp(-tt * 25)) * tt) * np.exp(-tt * dec)
    x += noise * band(r.standard_normal(n), 100, 2500, 2) * np.exp(-tt * 18)
    return x / np.abs(x).max()


def step(seed):
    r = np.random.default_rng(seed)
    n = int(SR * 0.12)
    tt = np.arange(n) / SR
    x = band(r.standard_normal(n), 300, 4000, 2) * np.exp(-tt * 55) + 0.4 * np.sin(2 * np.pi * 110 * tt) * np.exp(-tt * 40)
    return x / np.abs(x).max()


def whoosh(d=0.6, seed=0):
    r = np.random.default_rng(seed)
    n = int(SR * d)
    x = r.standard_normal(n)
    x = band(x, 300, 3000, 2) * np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return x / np.abs(x).max()


def wind_layer(seed, lo=150, hi=900):
    r = np.random.default_rng(seed)
    x = band(r.standard_normal((N, 2)), lo, hi, 2)
    k = np.arange(0, DUR + 2, 0.5)
    g = np.interp(t, k, 0.6 + 0.4 * r.random(len(k)))
    return x * g[:, None] / np.abs(x).max()


sfx = np.zeros((N, 2))
amb = np.zeros((N, 2))

# shop ticking ambience (many clocks, out of sync) while in the shop
shop_on = np.zeros(N)
for i in (1, 2, 5, 6, 7, 9, 10, 11, 12, 13, 14):
    shop_on[int(S[i] * SR):int(S[i + 1] * SR)] = 1
shop_on = movavg(shop_on, int(0.05 * SR))
ticks = [tick("small", k) for k in range(4)] + [tick("mid", 10 + k) for k in range(3)]
tickbed = np.zeros((N, 2))
for c in range(14):
    per = rng.uniform(0.45, 1.05)
    ph = rng.uniform(0, per)
    tk = ticks[c % len(ticks)]
    pan = rng.uniform(-0.8, 0.8)
    g = rng.uniform(0.2, 0.6)
    tt0 = ph
    while tt0 < DUR:
        put(tickbed, tk, tt0, g, pan)
        tt0 += per
amb += tickbed * shop_on[:, None] * db(-24)
# candle crackle in the shop
cr = np.zeros(N)
for k in rng.uniform(0, DUR, 500):
    i = int(k * SR)
    if i + 200 < N:
        cr[i:i + 200] += rng.standard_normal(200) * np.exp(-np.arange(200) / 30)
amb += np.column_stack([cr, cr * 0.7]) * shop_on[:, None] * db(-34)

# town wind / night ambience
town = np.zeros(N)
for i in (0, 3, 4, 8, 15, 16, 17, 28, 29, 30, 31, 32, 33, 34):
    town[int(S[i] * SR):int(S[i + 1] * SR)] = 1
town = movavg(town, int(0.05 * SR))
wind = wind_layer(3)
amb += wind * town[:, None] * db(-30)
amb += wind_layer(4, 400, 2500) * env([(0, 0), (S[15], 0), (S[15] + 0.3, 1), (S[18], 1), (S[18] + 0.1, 0), (DUR, 0)])[:, None] * db(-30)
# room: muffled wind + snow outside, lamp
room = np.zeros(N)
for i in range(18, 28):
    room[int(S[i] * SR):int(S[i + 1] * SR)] = 1
amb += band(wind_layer(5), None, 400, 2) * room[:, None] * db(-30)

# events
put(sfx, load(os.path.join(HERE, "sfx", "laugh.wav"))[: int(SR * 2.9)] * np.linspace(1, 1, int(SR * 2.9))[:, None], S[3] + 0.05, db(-12))
put(sfx, whoosh(0.5, 2), S[4] + 0.62 * (S[5] - S[4]) - 0.1, db(-20))
# hero clock ticks in the macro shots (backwards ticking)
for i in (5, 6):
    tt0 = S[i] + 0.05
    while tt0 < S[i + 1]:
        put(sfx, tick("mid", 3), tt0, db(-14))
        tt0 += 1.0 if i == 5 else 0.5
for k in range(8):
    put(sfx, tick("deep", 20 + k), S[7] + 0.05 + k * 0.25, db(-10 + k * 0.6))
# man dissolves
dust = load(os.path.join(HERE, "sfx", "dust.wav"))
put(sfx, dust, DIS_T0 - 0.1, db(-9))
# shop door + bell
put(sfx, load(os.path.join(HERE, "sfx", "bell.wav"))[: int(SR * 3.5)], S[9] + 0.15, db(-10))
# heartbeat: shot 14 onwards, getting faster
hb = heartbeat()
tt0 = S[13]
while tt0 < S[24]:
    rate = 1.0 if tt0 < S[15] else 0.75 if tt0 < S[19] else 0.6
    g = db(-8) if tt0 < S[14] else db(-14)
    put(sfx, hb, tt0, g)
    tt0 += rate
# grab + spin whoosh
put(sfx, whoosh(0.7, 4), S[14] + 0.6, db(-16))
# running footsteps (shop exit, street, into the room)
for a, b, per in ((S[14] + 1.3, S[15], 0.2), (S[15], S[18], 0.19), (S[18] + 0.3, S[18] + 2.6, 0.19)):
    tt0 = a
    k = 0
    while tt0 < b:
        put(sfx, step(k), tt0, db(-17), 0.2 * (1 if k % 2 else -1))
        tt0 += per
        k += 1
# accelerating ticks of grandma's clock (shots 15..25)
tt0 = S[12]
while tt0 < S[24] + 0.2:
    if tt0 < S[16]:
        per = 1.0
    else:
        per = max(0.09, 0.5 - (tt0 - S[16]) * 0.03)
    if tt0 >= S[24]:
        break
    g = db(-16) if tt0 < S[16] else db(-12)
    put(sfx, tick("small", 30), tt0, g)
    tt0 += per
# '30' and '10' accents
put(sfx, thud(45, 5, 0.2, 2), AT[17] - 0.05, db(-12))
put(sfx, thud(45, 5, 0.2, 3), AT[20] - 0.05, db(-10))
# door bursts open in the room: bang + gust
put(sfx, thud(55, 7, 0.9, 5), S[18] + 0.15, db(-6))
gust = band(np.random.default_rng(9).standard_normal((int(SR * 3), 2)), 200, 3000, 2)
gust *= np.concatenate([np.linspace(0, 1, int(SR * 0.1)), np.exp(-np.linspace(0, 3, int(SR * 2.9)))])[:, None]
put(sfx, gust / np.abs(gust).max(), S[18] + 0.15, db(-12))
# hug: warm swell handled in music; squeeze creak
put(sfx, whoosh(1.5, 7) * 0.5, S[22] + 0.2, db(-24))
# glass crack
put(sfx, load(os.path.join(HERE, "sfx", "crack.wav")), AT[23] + 0.2, db(-6))
# THE tick
big = tick("big", 50)
bigs = np.column_stack([big, big])
bigs = reverb(np.vstack([bigs, np.zeros((SR * 3, 2))]), 3.5, 0.5)
put(sfx, bigs, TICK_T, db(-5))
put(sfx, dust, TICK_T + 0.15, db(-12))
# hands go forward: soft forward ticks
tt0 = TICK_T + 1.0
while tt0 < S[28]:
    put(sfx, tick("mid", 60), tt0, db(-18))
    tt0 += 1.0
# wave over the town: shimmer + distant clocks chiming
put(sfx, dust, S[28], db(-8))
for k in range(5):
    n = int(SR * 3)
    tt_ = np.arange(n) / SR
    f = [523, 659, 784, 1046, 880][k]
    ch = (np.sin(2 * np.pi * f * tt_) + 0.3 * np.sin(2 * np.pi * f * 2.01 * tt_)) * np.exp(-tt_ * 1.5)
    put(sfx, ch, S[28] + 0.15 + k * 0.25, db(-24), (k - 2) * 0.3)
# morning: gentle birds (chirps)
for k in range(10):
    n = int(SR * 0.18)
    tt_ = np.arange(n) / SR
    f = 3200 + 900 * np.sin(2 * np.pi * 12 * tt_)
    ch = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt_ / tt_[-1])
    put(sfx, ch, S[29] + 0.3 + k * rng.uniform(0.5, 1.4), db(-32), rng.uniform(-0.7, 0.7))
# note: paper rustle
put(sfx, whoosh(0.6, 11) * 0.6, S[31] + 0.5, db(-26))
# backwards ticking at the end (shot 35-36)
tt0 = S[34]
while tt0 < DUR - 0.3:
    put(sfx, tick("deep", 70), tt0, db(-12) if tt0 > S[35] else db(-14))
    tt0 += 1.0

# end card: mouse clicks on like / subscribe / bell + a bell ding
T_END = S[35] + 1.0
for tc in (1.35, 2.25, 3.1):
    put(sfx, tick("small", 90), T_END + tc, db(-14))
put(sfx, np.column_stack([band(np.random.default_rng(91).standard_normal(int(SR * 0.3)), 2000, 8000, 2) * np.exp(-np.arange(int(SR * 0.3)) / SR * 30)] * 2), T_END + 1.35, db(-24))
n = int(SR * 1.6)
tt_ = np.arange(n) / SR
ding = sum(np.sin(2 * np.pi * f * tt_) * np.exp(-tt_ * d) * a_ for f, d, a_ in ((1320, 2.5, 1.0), (1980, 3.5, 0.5), (2640, 5, 0.3)))
for k in range(3):
    put(sfx, ding / np.abs(ding).max(), T_END + 3.1 + k * 0.12, db(-16 - 4 * k))
# ------------------------------------------------------------------ music (dark ambient, tension from shot 15)
def pad(freqs, detune=0.003, seed=0):
    r = np.random.default_rng(seed)
    x = np.zeros((N, 2))
    for f in freqs:
        for c in range(2):
            ph = r.uniform(0, 6.28)
            fm = f * (1 + detune * r.uniform(-1, 1))
            x[:, c] += np.sin(2 * np.pi * fm * t + ph + 0.3 * np.sin(2 * np.pi * 0.07 * t + ph))
    return x / len(freqs)


drone = pad([55, 82.4, 110, 130.8], 0.004, 1)            # A minor
drone = band(drone, None, 900, 2)
tension = pad([110, 116.5, 164.8, 174.6], 0.002, 2)        # clusters
tension *= (0.6 + 0.4 * np.sin(2 * np.pi * (2.0 + 2.0 * np.clip((t - S[14]) / 20, 0, 1)) * t))[:, None]
rise = np.zeros((N, 2))
f_r = 220 * 2 ** (np.clip(t - S[14], 0, 25) / 25 * 1.0)
rise[:, 0] = np.sin(2 * np.pi * np.cumsum(f_r) / SR)
rise[:, 1] = np.sin(2 * np.pi * np.cumsum(f_r * 1.004) / SR)
warm = pad([65.4, 130.8, 164.8, 196.0, 261.6, 329.6], 0.003, 3)   # C major resolution
warm = band(warm, None, 2500, 2)
morning = pad([87.3, 174.6, 220, 261.6, 349.2], 0.003, 4)         # F major, airy
ominous = pad([41.2, 43.65, 61.7, 82.4], 0.006, 5)                  # low dissonant
ominous = band(ominous, None, 500, 2)
pulse = np.zeros((N, 2))
for tt0 in np.arange(S[14], S[24], 0.5):
    put(pulse, thud(42, 10, 0.05, int(tt0 * 10)), tt0, 0.5)

g_drone = env([(0, 0), (1.5, 1), (S[14], 1), (S[24], 0.9), (S[25] - 0.1, 0.8), (S[25], 0), (S[29], 0), (S[29] + 2, 0.0), (DUR, 0)])
g_tension = env([(0, 0), (S[14], 0), (S[16], 0.5), (S[20], 0.8), (S[24], 1.0), (S[25] - 0.05, 1.0), (S[25], 0), (DUR, 0)])
g_rise = env([(0, 0), (S[15], 0), (S[24], 0.5), (S[25] - 0.05, 0.6), (S[25], 0), (DUR, 0)])
g_warm = env([(0, 0), (TICK_T, 0), (TICK_T + 1.5, 1), (S[29], 1), (S[29] + 2, 0.6), (S[33], 0.4), (S[34], 0), (DUR, 0)])
g_morn = env([(0, 0), (S[29], 0), (S[29] + 2, 0.8), (S[33], 0.8), (S[34], 0), (DUR, 0)])
g_omin = env([(0, 0), (S[33] + 1.0, 0), (S[34], 1), (DUR - 1.0, 1), (DUR, 0)])
music = (drone * g_drone[:, None] * 0.5 + tension * g_tension[:, None] * 0.28 + rise * g_rise[:, None] * 0.06
         + warm * g_warm[:, None] * 0.35 + morning * g_morn[:, None] * 0.22 + ominous * g_omin[:, None] * 0.6
         + pulse * g_tension[:, None] * 0.8)
music = reverb(music, 3.0, 0.3, 4)

# ------------------------------------------------------------------ mix
# full silence for "Тиша" (shots 26-27 until the tick), except the voice
quiet = env([(0, 1), (S[25] - 0.05, 1), (S[25] + 0.05, 0.0), (TICK_T - 0.02, 0.0), (TICK_T, 1), (DUR, 1)])
# silence after the hand reaches zero (shot 8)
zero = env([(0, 1), (S[7] + 1.85, 1), (S[7] + 1.9, 0.05), (S[8] - 0.02, 0.05), (S[8], 1), (DUR, 1)])
vol_env = np.abs(voice).max(1)
duck = movavg(vol_env, int(0.3 * SR))
duck = 1 - 0.45 * np.clip(duck * 6, 0, 1)
mix = voice * db(-1) + (music * db(-13) * duck[:, None] + amb * duck[:, None] + sfx * db(-2)) * (quiet * zero)[:, None]
# end fade
mix *= env([(0, 0), (0.05, 1), (DUR - 0.6, 1), (DUR, 0)])[:, None]
mix = np.tanh(mix * 0.9)
mix /= np.abs(mix).max() / 0.9
wavfile.write(os.path.join(HERE, "mix.wav"), SR, (mix * 32767).astype(np.int16))
print("mix.wav", mix.shape, "words", len(words))
