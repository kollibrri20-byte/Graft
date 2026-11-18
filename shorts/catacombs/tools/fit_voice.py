"""Fit a new narration (one take of the whole script) onto the existing animation timing.
Splits the take at its 4 longest pauses into the 5 script lines, time-stretches each line to the
duration that line has in words.json (the timing the video was rendered to), and rebuilds words.json
proportionally inside each line.  python fit_voice.py new_take.mp3 out_dir"""
import json, os, subprocess, sys, tempfile
import numpy as np
src, out = sys.argv[1], sys.argv[2]
SR = 44100
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
x = np.frombuffer(raw, np.float32).copy()
lines = [l.strip() for l in open(os.path.join(out, "script.txt"), encoding="utf-8") if l.strip()]
old = json.load(open(os.path.join(out, "words.json")))
# old per-line spans
spans, k = [], 0
for l in lines:
    n = len(l.split())
    spans.append((old[k]["s"], old[k + n - 1]["e"] + 0.03)); k += n
# silence detection on 20 ms frames
hop = SR // 50
env = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, mode="same"))[::hop]
loud = env > max(1e-4, env.max() * 0.04)
idx = np.nonzero(loud)[0]
a, b = idx[0], idx[-1]
gaps, run = [], None
for i in range(a, b + 1):
    if not loud[i]:
        run = i if run is None else run
    elif run is not None:
        gaps.append((i - run, run, i)); run = None
cuts = sorted(sorted(gaps, reverse=True)[:len(lines) - 1], key=lambda g: g[1])
bounds = [a] + [c for g in cuts for c in (g[1], g[2])] + [b + 1]
segs = [(bounds[2 * i] * hop, bounds[2 * i + 1] * hop) for i in range(len(lines))]
total = max(old[-1]["e"] + 1.0, len(x) / SR)
y = np.zeros(int((total + 1) * SR), np.float32)
words = []
tmp = tempfile.mkdtemp()
for (s0, s1), (t0, t1), line in zip(segs, spans, lines):
    seg = x[max(0, s0 - 600): s1 + 1500]
    want = t1 - t0
    ratio = (len(seg) / SR) / want
    ratio = min(max(ratio, 1.0), 1.25)       # never slow a real voice down; only tighten a long line a little
    p_in, p_out = os.path.join(tmp, "i.f32"), os.path.join(tmp, "o.f32")
    seg.tofile(p_in)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", p_in,
                    "-af", f"atempo={ratio:.4f}", "-f", "f32le", p_out], check=True)
    z = np.fromfile(p_out, np.float32)
    i0 = int(t0 * SR)
    y[i0:i0 + len(z)] += z[: len(y) - i0]
    d = len(z) / SR
    toks = line.split()
    w = np.array([len(t.strip(".,!?")) + 2 for t in toks], float)
    e = np.concatenate([[0], np.cumsum(w)]) / w.sum() * d
    for j, t in enumerate(toks):
        words.append({"w": t, "s": round(t0 + e[j], 3), "e": round(t0 + e[j + 1] - 0.03, 3)})
    print(f"{line[:40]:40s} take {len(seg)/SR:.2f}s -> slot {want:.2f}s (x{ratio:.2f})")
y = y / max(1e-6, np.abs(y).max()) * 0.9
import wave
with wave.open(os.path.join(out, "voice.wav"), "wb") as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
    f.writeframes((y * 32767).astype(np.int16).tobytes())
json.dump(words, open(os.path.join(out, "words.json"), "w"), ensure_ascii=False, indent=1)
print("voice.wav + words.json rewritten")
