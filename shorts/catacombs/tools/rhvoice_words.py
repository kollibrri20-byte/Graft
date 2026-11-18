"""Offline Ukrainian narration (RHVoice) -> voice.wav + words.json in the eleven.py format.
Each script line is synthesized separately, silence trimmed, joined with pauses; word times are
spread inside each line by character length (fine for 1-3 word captions and beat timing).
  python rhvoice_words.py script.txt out_dir [--voice volodymyr]"""
import json, os, subprocess, sys, wave, tempfile
import numpy as np

script, out = sys.argv[1], sys.argv[2]
vname = sys.argv[sys.argv.index("--voice") + 1] if "--voice" in sys.argv else "volodymyr"
SR = 24000
lines = [l.strip() for l in open(script, encoding="utf-8") if l.strip()]
LEAD, GAP = 0.35, 0.32
audio = [np.zeros(int(LEAD * SR), np.float32)]
t = LEAD
words = []
tmp = tempfile.mkdtemp()
for i, line in enumerate(lines):
    p = os.path.join(tmp, f"{i}.wav")
    subprocess.run(["RHVoice-test", "-p", vname, "-r", "88", "-t", "92", "-R", str(SR), "-o", p],
                   input=line.encode(), check=True)
    with wave.open(p) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    env = np.abs(x) > 0.01
    idx = np.nonzero(env)[0]
    x = x[max(0, idx[0] - 240): idx[-1] + 2400]
    dur = len(x) / SR
    toks = line.split()
    weights = np.array([len(w.strip(".,!?")) + 2 for w in toks], float)
    edges = np.concatenate([[0], np.cumsum(weights)]) / weights.sum() * dur
    for k, w in enumerate(toks):
        words.append({"w": w, "s": round(t + edges[k], 3), "e": round(t + edges[k + 1] - 0.03, 3)})
    audio.append(x)
    t += dur
    gap = GAP if line.endswith(",") else GAP + 0.25
    audio.append(np.zeros(int(gap * SR), np.float32))
    t += gap
y = np.concatenate(audio)
y = y / max(1e-6, np.abs(y).max()) * 0.9
os.makedirs(out, exist_ok=True)
with wave.open(os.path.join(out, "voice.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((y * 32767).astype(np.int16).tobytes())
json.dump(words, open(os.path.join(out, "words.json"), "w"), ensure_ascii=False, indent=1)
print(f"voice.wav {t:.2f}s, {len(words)} words")
