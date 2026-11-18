"""More natural offline narration: RHVoice (Ukrainian 'volodymyr') driven by per-line SSML with explicit
stress marks (+), phrase-level rate/pitch contours and pauses; then a voice chain (slightly lower pitch with
formants kept, warm EQ, gentle compression, short stone-room reverb). Each line is placed at the start of
its slot in the timing the animation was rendered to (words_rhvoice.json), so no re-render is needed.
  python tts_natural.py <project_dir>   (needs /etc/RHVoice/RHVoice.conf: languages.Ukrainian.stress_marker=+)"""
import json, os, subprocess, sys, tempfile, wave
import numpy as np
P = sys.argv[1]
SR = 44100
plain = [l.strip() for l in open(os.path.join(P, "script.txt"), encoding="utf-8") if l.strip()]
ssml = [l.strip() for l in open(os.path.join(P, "script_ssml.txt"), encoding="utf-8") if l.strip()]
old = json.load(open(os.path.join(P, "words_rhvoice.json")))
spans, k = [], 0
for l in plain:
    n = len(l.split()); spans.append((old[k]["s"], old[k + n - 1]["e"] + 0.03)); k += n
tmp = tempfile.mkdtemp()
CHAIN = ("highpass=f=70,rubberband=pitch=0.95:formant=preserved,"
         "equalizer=f=140:t=q:w=1:g=3,equalizer=f=320:t=q:w=1.2:g=-2,equalizer=f=3200:t=q:w=1.5:g=2.5,"
         "equalizer=f=7500:t=q:w=2:g=-3,acompressor=threshold=0.12:ratio=2.5:attack=8:release=120:makeup=1.5,"
         "aecho=0.85:0.5:38|71:0.16|0.09")
nxt = [s for s, _ in spans[1:]] + [old[-1]["e"] + 2.0]
y = np.zeros(int((old[-1]["e"] + 3) * SR), np.float32)
words = []
for i, (line, sm, (t0, t1), tn) in enumerate(zip(plain, ssml, spans, nxt)):
    w_ = os.path.join(tmp, f"{i}.wav")
    subprocess.run(["RHVoice-test", "-s", "-p", "volodymyr", "-R", "24000", "-o", w_],
                   input=f"<speak>{sm}</speak>".encode(), check=True)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", w_, "-af", CHAIN, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    z = np.frombuffer(raw, np.float32).copy()
    on = np.nonzero(np.abs(z) > 0.01)[0]
    z = z[max(0, on[0] - 300):]
    tail = len(z)                                   # keep the reverb tail but measure speech end
    speech = (on[-1] - on[0]) / SR
    room = tn - t0 - 0.12
    if speech > room:                               # only tighten a line that would run into the next one
        r = min(1.2, speech / room)
        p_in, p_out = os.path.join(tmp, "i.f32"), os.path.join(tmp, "o.f32")
        z.tofile(p_in)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", p_in,
                        "-af", f"rubberband=tempo={r:.4f}", "-f", "f32le", p_out], check=True)
        z = np.fromfile(p_out, np.float32); speech /= r
    i0 = int(t0 * SR)
    y[i0:i0 + len(z)] += z[: len(y) - i0]
    toks = line.split()
    wt = np.array([len(t.strip(".,!?")) + 2 for t in toks], float)
    e = np.concatenate([[0], np.cumsum(wt)]) / wt.sum() * speech
    for j, t in enumerate(toks):
        words.append({"w": t, "s": round(t0 + e[j], 3), "e": round(t0 + e[j + 1] - 0.03, 3)})
    print(f"{line[:42]:42s} speech {speech:.2f}s  slot {t1 - t0:.2f}s  room {room:.2f}s")
y = y / max(1e-6, np.abs(y).max()) * 0.9
with wave.open(os.path.join(P, "voice.wav"), "wb") as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
    f.writeframes((y * 32767).astype(np.int16).tobytes())
json.dump(words, open(os.path.join(P, "words.json"), "w"), ensure_ascii=False, indent=1)
print("voice.wav + words.json written")
