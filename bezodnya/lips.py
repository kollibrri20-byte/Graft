"""Ознаки для лікпсинку з voice.wav: на кожні 1/24 с — відкритість рота, ширина/округлість."""
import json, sys
import numpy as np
from scipy.io import wavfile
sr, v = wavfile.read(sys.argv[1]); v = v.astype(np.float32) / 32768
hop = sr // 24; win = int(sr * 0.05)
n = len(v) // hop
rms = np.zeros(n); cen = np.zeros(n); low = np.zeros(n)
fr = np.fft.rfftfreq(win, 1 / sr)
for i in range(n):
    a = max(0, i * hop - win // 2); x = v[a:a + win]
    if len(x) < win: x = np.pad(x, (0, win - len(x)))
    sp = np.abs(np.fft.rfft(x * np.hanning(win)))
    rms[i] = np.sqrt((x ** 2).mean())
    band = sp[(fr > 200) & (fr < 4000)]
    cen[i] = (sp * fr)[(fr > 200) & (fr < 4000)].sum() / (band.sum() + 1e-9)
    low[i] = sp[(fr > 200) & (fr < 900)].sum() / (band.sum() + 1e-9)
ref = np.percentile(rms[rms > 0.005], 90)
op = np.clip(rms / ref, 0, 1.2) ** 0.8
op[rms < 0.006] = 0
# згладити, але швидко відкривати
sm = np.zeros(n)
for i in range(1, n):
    k = 0.65 if op[i] > sm[i - 1] else 0.45
    sm[i] = sm[i - 1] + (op[i] - sm[i - 1]) * k
c = (cen - 900) / 1600
wide = np.clip(c, 0, 1) * (sm > 0.05)
rnd = np.clip((low - 0.55) / 0.3, 0, 1) * (sm > 0.05)
json.dump(dict(fps=24, open=np.round(sm, 3).tolist(), wide=np.round(wide, 3).tolist(),
               round=np.round(rnd, 3).tolist()), open(sys.argv[2], "w"))
print(n, "frames")
