"""Put synthesized lines on a video's storyboard timeline -> voice.wav (48k stereo) + words.json."""
import json, os, re, subprocess, sys
import numpy as np
SR = 48000


def load(path, af=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if af:
        cmd += ["-af", af]
    cmd += ["-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).copy()


def trim(x, thr=0.01):
    idx = np.where(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 600): idx[-1] + 2400] if len(idx) else x


def fit(path, limit, slow=1.12, extra_af=None):
    x = trim(load(path, extra_af))
    d = len(x) / SR
    tempo = slow if d / slow <= limit else max(slow, min(1.35, d / max(0.4, limit)))
    af = f"atempo={tempo:.3f}" + ("," + extra_af if extra_af else "")
    y = trim(load(path, af))
    return y


proj, lines_dir, script, out_dir, total = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
texts = [l.strip().replace("WHISPER:", "").replace("|", " — ") for l in open(script) if l.strip()]
texts = [t.replace("́", "") for t in texts]
if proj == "mirrors":
    SL = [0, 2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90]
    starts = [s + 0.25 for s in SL[:-1]]
    limits = [SL[i + 1] - SL[i] - 0.35 for i in range(36)]
else:
    L = json.load(open(os.path.join(out_dir, "lines_raw.json")))
    starts = [l["at"] for l in L]
    limits = [(starts[i + 1] - starts[i] - 0.15) if i < 35 else total - starts[i] - 1.0 for i in range(36)]
N = int(total * SR)
voice = np.zeros(N, np.float32)
words = []
prev_end = 0.0
for i in range(36):
    p = os.path.join(lines_dir, f"l{i:02d}.wav")
    pw = os.path.join(lines_dir, f"l{i:02d}_w.wav")
    t0 = max(starts[i], prev_end + 0.1)
    lim = max(0.8, (starts[i + 1] if i < 35 else total - 1.2) - t0 - 0.1)
    limits[i] = lim
    starts[i] = t0
    segs = []
    if os.path.exists(pw):
        w = fit(pw, limits[i] * 0.55, 0.85, "highpass=f=350,lowpass=f=6000,aecho=0.8:0.75:70|140|260:0.45|0.3|0.2,volume=0.75")
        segs.append((t0, w))
        t0 += len(w) / SR + 0.15
        n = fit(p, max(0.6, starts[i] + limits[i] - t0))
        segs.append((t0, n))
    else:
        segs.append((t0, fit(p, limits[i])))
    end = t0
    for at, x in segs:
        x = x / (np.abs(x).max() + 1e-9) * 0.85
        a = int(at * SR)
        b = min(N, a + len(x))
        if b > a:
            voice[a:b] += x[: b - a]
        end = at + len(x) / SR
    prev_end = end
    # approximate word timing across the whole line
    ws = [w for w in texts[i].replace("...", " ").replace("…", " ").split() if re.sub(r"[^\w]", "", w)]
    lens = np.array([len(re.sub(r"[^\w]", "", w)) + 1.5 for w in ws])
    dur = end - starts[i]
    edges = np.concatenate([[0], np.cumsum(lens)]) / lens.sum() * dur
    for k, w in enumerate(ws):
        words.append({"w": w.strip(",.:;—«»?"), "raw": w, "s": round(starts[i] + edges[k], 3), "e": round(starts[i] + edges[k + 1], 3), "line": i})
    print(i, round(starts[i], 2), round(dur, 2), round(limits[i], 2))
# gentle EQ/warmth + loudness
import scipy.io.wavfile as wf
st = np.column_stack([voice, voice])
tmp = os.path.join(out_dir, "voice_tmp.wav")
wf.write(tmp, SR, (np.clip(st, -1, 1) * 32767).astype(np.int16))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", "highpass=f=70,equalizer=f=180:t=q:w=1:g=2.5,equalizer=f=3500:t=q:w=1:g=1.5,acompressor=threshold=0.2:ratio=3",
                os.path.join(out_dir, "voice.wav")], check=True)
os.remove(tmp)
json.dump(words, open(os.path.join(out_dir, "words.json"), "w"), ensure_ascii=False, indent=0)
print("done", len(words))
