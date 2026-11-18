"""Soundtrack for «Крамниця дзеркал»: rain bed, dark ambient score (tension from shot 14, silence in 25,
warm in 30-31, hard stop at 33), procedural + reused ElevenLabs effects. Narration is optional:
if voice.wav exists (already on the storyboard timeline) it is mixed in and ducks the music. -> mix.wav"""
import os

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
DUR = 92.8
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(3)
S = [0, 2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82,
     85, 87, DUR]
IMPACT_T = 53.55


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


def env(points):
    ts, vs = zip(*points)
    return np.interp(t, ts, vs)


def db(x):
    return 10 ** (x / 20)


def put(buf, x, at, gain=1.0, pan=0.0):
    if x.ndim == 1:
        x = np.column_stack([x * (1 - max(0, pan)), x * (1 + min(0, pan))])
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * gain


def movavg(x, n):
    c = np.cumsum(np.concatenate([np.zeros(n), x, np.zeros(n)]))
    y = (c[n:] - c[:-n]) / n
    return y[n // 2: n // 2 + len(x)]


def reverb(x, secs=2.5, wet=0.35, seed=1):
    r = np.random.default_rng(seed)
    n = int(SR * secs)
    tt = np.arange(n) / SR
    ir = r.standard_normal((n, 2)) * np.exp(-tt * 4.5 / secs)[:, None]
    ir = band(ir, 200, 7000, 2)
    ir /= np.abs(ir).sum(0) ** 0.5 * 8
    y = np.column_stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)])
    return x * (1 - wet) + y * wet * 3


def mask(shots):
    m = np.zeros(N)
    for i in shots:
        m[int(S[i] * SR):int(S[i + 1] * SR)] = 1
    return movavg(m, int(0.04 * SR))


def thud(f=60, dec=8, noise=0.4, seed=0, n_s=1.2):
    n = int(SR * n_s)
    tt = np.arange(n) / SR
    r = np.random.default_rng(seed)
    x = np.sin(2 * np.pi * (f + 60 * np.exp(-tt * 25)) * tt) * np.exp(-tt * dec)
    x += noise * band(r.standard_normal(n), 100, 2500, 2) * np.exp(-tt * 18)
    return x / np.abs(x).max()


def knock(seed=0):
    n = int(SR * 0.25)
    tt = np.arange(n) / SR
    r = np.random.default_rng(seed)
    x = np.sin(2 * np.pi * 180 * tt) * np.exp(-tt * 40) + 0.5 * band(r.standard_normal(n), 800, 4000, 2) * np.exp(-tt * 90)
    x += 0.4 * np.sin(2 * np.pi * 1900 * tt) * np.exp(-tt * 30)  # glassy ring
    return x / np.abs(x).max()


def creak():
    n = int(SR * 1.3)
    tt = np.arange(n) / SR
    f = 140 + 60 * np.sin(2 * np.pi * 0.8 * tt) + 20 * np.sin(2 * np.pi * 7 * tt)
    pulses = (np.sin(2 * np.pi * np.cumsum(f) / SR) > 0.85).astype(float)
    x = band(pulses * (0.5 + 0.5 * np.random.default_rng(4).random(n)), 200, 2500, 2) * np.sin(np.pi * tt / tt[-1])
    return x / np.abs(x).max()


def tinkle(n_s=3.0, seed=0, dens=40):
    n = int(SR * n_s)
    x = np.zeros(n)
    r = np.random.default_rng(seed)
    for k in range(int(dens * n_s)):
        at = int(r.uniform(0, n - SR * 0.3))
        f = r.uniform(2500, 7000)
        m = int(SR * 0.25)
        tt = np.arange(m) / SR
        x[at:at + m] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * r.uniform(15, 40)) * r.uniform(0.2, 1)
    return x / np.abs(x).max()


def whoosh(d=0.6, seed=0):
    r = np.random.default_rng(seed)
    n = int(SR * d)
    x = band(r.standard_normal(n), 300, 3000, 2) * np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return x / np.abs(x).max()


def heartbeat():
    n = int(SR * 0.9)
    tt = np.arange(n) / SR

    def th(t0, a):
        t2 = np.clip(tt - t0, 0, None)
        return a * np.sin(2 * np.pi * (48 + 30 * np.exp(-t2 * 20)) * t2) * np.exp(-t2 * 14) * (tt >= t0)
    return band(th(0, 1.0) + th(0.24, 0.7), None, 180, 2)


sfx = np.zeros((N, 2))
amb = np.zeros((N, 2))
# rain: outdoors loud, indoors muffled on the windows
rain = band(rng.standard_normal((N, 2)), 800, 9000, 2)
rain += 0.5 * band(rng.standard_normal((N, 2)), 150, 900, 2)
rain /= np.abs(rain).max()
out_m = mask([0, 5, 18, 28, 29, 30])
door_open = env([(0, 0), (S[6], 0), (S[6] + 0.2, 1), (S[8] - 0.5, 1), (S[8], 0), (DUR, 0)])
amb += rain * (out_m * db(-20) + np.maximum(door_open * db(-24), db(-36)) * (1 - out_m))[:, None]
# drips / candle in the shop
shop_m = mask([i for i in range(36) if i not in (0, 5, 16, 17, 18, 28, 29, 30, 31, 32, 33, 34, 35)])
cr = np.zeros(N)
for k in rng.uniform(0, DUR, 400):
    i = int(k * SR)
    if i + 200 < N:
        cr[i:i + 200] += rng.standard_normal(200) * np.exp(-np.arange(200) / 30)
amb += np.column_stack([cr, cr * 0.7]) * shop_m[:, None] * db(-36)

bell = load(os.path.join(HERE, "sfx", "bell.wav"))[: int(SR * 3.5)]
put(sfx, bell, S[4] + 0.6, db(-12))
put(sfx, load(os.path.join(HERE, "sfx", "laugh.wav"))[: int(SR * 2.4)], S[4] + 0.05, db(-14))
# door bursts open + bell + gust
put(sfx, thud(55, 7, 0.9, 5), S[6] + 0.12, db(-7))
put(sfx, bell, S[6] + 0.15, db(-10))
gust = band(np.random.default_rng(9).standard_normal((int(SR * 2.5), 2)), 200, 3000, 2)
gust *= np.concatenate([np.linspace(0, 1, int(SR * 0.1)), np.exp(-np.linspace(0, 3, int(SR * 2.4)))])[:, None]
put(sfx, gust / np.abs(gust).max(), S[6] + 0.12, db(-14))
# water shaken off
put(sfx, tinkle(1.2, 2, 30) * 0.3, S[7] + 0.1, db(-26))
# cloth slides
put(sfx, whoosh(1.2, 3), S[8] + 0.3, db(-24))
# knocks from inside the mirror
for k in range(5):
    put(sfx, knock(k), S[10] + 0.05 + k * 0.31, db(-6))
# paper rustle
put(sfx, whoosh(0.5, 6) * 0.6, S[11] + 0.2, db(-22))
# floor creak behind
put(sfx, creak(), S[13] + 0.2, db(-8))
# heartbeat (14..21)
hb = heartbeat()
tt0 = S[13] + 1.2
while tt0 < S[21]:
    put(sfx, hb, tt0, db(-14))
    tt0 += 0.85 if tt0 < S[18] else 0.62
# muffled shouting behind glass (16-17)
sh = band(load(os.path.join(HERE, "sfx", "laugh.wav")), 150, 900, 2)
put(sfx, sh[: int(SR * 5)], S[16], db(-16))
# fingers stretching
put(sfx, creak() * 0.6, S[19] + 0.3, db(-18))
# stool grab + spin whoosh, impact, shatter
put(sfx, whoosh(0.8, 7), S[20] + 0.4, db(-14))
put(sfx, thud(70, 9, 1.0, 8), IMPACT_T, db(-3))
crack = load(os.path.join(HERE, "sfx", "crack.wav"))
put(sfx, crack, IMPACT_T, db(-2))
slow = band(np.repeat(tinkle(1.5, 9, 60), 3)[:, None] * np.ones((1, 2)), 300, 6000, 2)  # pitched-down slow-mo tinkle
put(sfx, reverb(slow / np.abs(slow).max(), 3, 0.5), S[22] + 0.1, db(-10))
# faces gasping (24): breathy noise swells
for k in range(4):
    g = band(np.random.default_rng(20 + k).standard_normal(int(SR * 0.7)), 500, 2500, 2) * np.sin(np.pi * np.linspace(0, 1, int(SR * 0.7)))
    put(sfx, g / np.abs(g).max(), S[23] + 0.3 + k * 0.5, db(-22), (k - 1.5) * 0.4)
# chain of cracks (26)
for k in range(9):
    put(sfx, crack[: int(SR * 1.5)] * (0.6 + 0.4 * rng.random()), S[25] + 0.2 + k * 0.22, db(-8 - k * 0.5), rng.uniform(-0.8, 0.8))
put(sfx, reverb(np.column_stack([tinkle(3, 30, 50)] * 2), 3, 0.4), S[25] + 0.4, db(-14))
# people stepping out: liquid
liq = band(np.random.default_rng(31).standard_normal((int(SR * 2.5), 2)), 200, 1200, 2) * (0.5 + 0.5 * np.sin(2 * np.pi * 6 * np.arange(int(SR * 2.5)) / SR))[:, None]
put(sfx, liq / np.abs(liq).max(), S[26] + 0.1, db(-18))
# Veyl dissolves
put(sfx, load(os.path.join(HERE, "sfx", "dust.wav")), S[27] + 0.3, db(-6))
# running home + lanterns
for k in range(int(2 / 0.19)):
    put(sfx, band(np.random.default_rng(k).standard_normal(int(SR * 0.1)), 300, 4000, 2) * np.exp(-np.arange(int(SR * 0.1)) / SR * 50), S[28] + k * 0.19, db(-18))
# knocking on the hallway mirror (34)
for k in range(5):
    put(sfx, band(knock(40 + k), None, 900, 2), S[33] + 0.1 + k * 0.33, db(-6))

# ------------------------------------------------------------------ music
def pad(freqs, detune=0.003, seed=0):
    r = np.random.default_rng(seed)
    x = np.zeros((N, 2))
    for f in freqs:
        for c in range(2):
            ph = r.uniform(0, 6.28)
            x[:, c] += np.sin(2 * np.pi * f * (1 + detune * r.uniform(-1, 1)) * t + ph + 0.3 * np.sin(2 * np.pi * 0.07 * t + ph))
    return x / len(freqs)


drone = band(pad([49.0, 73.4, 98.0, 116.5], 0.004, 1), None, 900, 2)        # G minor, dark
tension = pad([98.0, 103.8, 146.8, 155.6], 0.002, 2) * (0.6 + 0.4 * np.sin(2 * np.pi * (1.5 + 2.5 * np.clip((t - S[13]) / 25, 0, 1)) * t))[:, None]
glass = pad([1568, 1661, 2349], 0.001, 6) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t))[:, None]   # eerie glassy shimmer
warm = band(pad([65.4, 130.8, 164.8, 196.0, 261.6], 0.003, 3), None, 2500, 2)
ominous = band(pad([41.2, 43.65, 61.7, 82.4], 0.006, 5), None, 500, 2)
g_drone = env([(0, 0), (1.5, 1), (S[24] - 0.05, 1), (S[24], 0), (S[25], 0), (S[25] + 0.5, 0.8), (S[28], 0.6), (S[29], 0), (DUR, 0)])
g_tens = env([(0, 0), (S[13], 0), (S[16], 0.6), (S[22], 1.0), (S[24] - 0.05, 1.0), (S[24], 0), (S[25], 0), (S[25] + 0.3, 0.7), (S[28], 0), (DUR, 0)])
g_glass = env([(0, 0.4), (S[13], 0.4), (S[24] - 0.05, 0.7), (S[24], 0), (S[25] + 0.3, 0.8), (S[28], 0), (S[32], 0), (S[32] + 0.2, 0.6), (DUR, 0.5)])
g_warm = env([(0, 0), (S[28], 0), (S[29], 0.8), (S[32] - 0.05, 0.8), (S[32], 0), (DUR, 0)])
g_omin = env([(0, 0), (S[32], 0), (S[32] + 0.1, 1), (S[35] - 0.05, 1), (S[35], 0.4), (DUR - 1, 0.6), (DUR, 0)])
music = drone * g_drone[:, None] * 0.5 + tension * g_tens[:, None] * 0.28 + glass * g_glass[:, None] * 0.05 + warm * g_warm[:, None] * 0.35 + \
    ominous * g_omin[:, None] * 0.6
music = reverb(music, 3.0, 0.3, 4)

# end card clicks + ding
T_END = S[35] + 1.0
for tc in (1.35, 2.25, 3.1):
    put(sfx, knock(90) * 0.5, T_END + tc, db(-16))
n = int(SR * 1.6)
tt_ = np.arange(n) / SR
ding = sum(np.sin(2 * np.pi * f * tt_) * np.exp(-tt_ * d) * a for f, d, a in ((1320, 2.5, 1.0), (1980, 3.5, 0.5), (2640, 5, 0.3)))
put(sfx, ding / np.abs(ding).max(), T_END + 3.1, db(-16))

voice = np.zeros((N, 2))
vp = os.path.join(HERE, "voice.wav")
if os.path.exists(vp):
    v = load(vp)
    voice[: min(N, len(v))] = v[:N]
quiet = env([(0, 1), (S[24] + 0.02, 1), (S[24] + 0.1, 0.0), (S[25] - 0.05, 0.0), (S[25], 1), (DUR, 1)])
vol = movavg(np.abs(voice).max(1), int(0.3 * SR))
duck = 1 - 0.45 * np.clip(vol * 6, 0, 1)
mix = voice + (music * db(-11) * duck[:, None] + amb * duck[:, None] + sfx * db(-2)) * quiet[:, None]
mix *= env([(0, 0), (0.05, 1), (DUR - 0.6, 1), (DUR, 0)])[:, None]
mix = np.tanh(mix * 0.9)
mix /= np.abs(mix).max() / 0.9
wavfile.write(os.path.join(HERE, "mix.wav"), SR, (mix * 32767).astype(np.int16))
print("mix.wav", DUR)
