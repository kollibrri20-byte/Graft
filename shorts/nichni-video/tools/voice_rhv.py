"""Offline Ukrainian narration with RHVoice -> voice.wav (48 kHz mono) + words.json.

  python3 tools/voice_rhv.py script.txt . --rhv <dir with usr/bin/RHVoice-test> [--voice volodymyr]

Each sentence is synthesised on its own, so sentence boundaries are exact. Inside a sentence the
words are spread by syllable count, split at the real pauses found in the audio (commas, dashes).
Beat index 15 (the double's whisper) gets a whisper effect.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
import wave

import numpy as np

SR = 48000
VOW = set("аеєиіїоуюяАЕЄИІЇОУЮЯ")
WHISPER_BEATS = {15}
# extra silence (s) BEFORE a beat, for drama
PAUSE_BEFORE = {1: 0.5, 9: 0.6, 12: 0.9, 13: 0.4, 15: 0.8, 16: 1.0, 17: 0.9, 18: 0.5, 19: 0.6, 20: 0.7, 21: 1.1}


def sentences(line):
    parts = re.findall(r"[^.!?…:]+(?:[.!?…:]+[»\"]?|$)", line)
    return [p.strip() for p in parts if p.strip()]


def read_wav(p):
    with wave.open(p) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(1)
    if sr != SR:
        t_old = np.arange(len(x)) / sr
        t_new = np.arange(int(len(x) * SR / sr)) / SR
        x = np.interp(t_new, t_old, x).astype(np.float32)
    return x


def env_db(x, win=0.01):
    n = int(SR * win)
    m = len(x) // n
    e = np.sqrt((x[: m * n].reshape(m, n) ** 2).mean(1) + 1e-10)
    return 20 * np.log10(e), n


def trim(x):
    db, n = env_db(x)
    on = np.where(db > db.max() - 40)[0]
    a, b = max(0, on[0] * n - int(0.02 * SR)), min(len(x), (on[-1] + 1) * n + int(0.04 * SR))
    return x[a:b]


def gaps(x, min_len=0.09):
    db, n = env_db(x)
    quiet = db < db.max() - 32
    out, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if (j - i) * n / SR >= min_len and i > 0 and j < len(quiet):
                out.append((i * n / SR, j * n / SR))
            i = j
        else:
            i += 1
    return out


def syl(w):
    return max(1, sum(c in VOW for c in w))


def word_times(text, x):
    words = text.split()
    dur = len(x) / SR
    brk = [k for k, w in enumerate(words[:-1]) if re.search(r"[,—–;]$", w) or words[k + 1] in ("—", "–")]
    g = sorted(gaps(x), key=lambda ab: ab[0] - ab[1])[: len(brk)]
    g = sorted(g)
    segs, cuts = [], []
    if len(g) == len(brk) and brk:
        start_w, t0 = 0, 0.0
        for k, (a, b) in zip(brk, g):
            segs.append((start_w, k + 1, t0, a))
            start_w, t0 = k + 1, b
        segs.append((start_w, len(words), t0, dur))
    else:
        segs.append((0, len(words), 0.0, dur))
    out = []
    for w0, w1, t0, t1 in segs:
        ws = words[w0:w1]
        wt = np.array([syl(w) + 0.6 for w in ws], float)
        edges = t0 + (t1 - t0) * np.concatenate([[0], np.cumsum(wt) / wt.sum()])
        for k, w in enumerate(ws):
            out.append({"w": w, "s": float(edges[k]), "e": float(edges[k + 1] - 0.02)})
    return out


def whisper(x):
    """Phase-randomised STFT = breathy whisper, plus a faint dry copy for intelligibility."""
    n, hop = 512, 128
    win = np.hanning(n).astype(np.float32)
    rng = np.random.default_rng(7)
    pad = np.concatenate([np.zeros(n), x, np.zeros(n)])
    y = np.zeros_like(pad)
    norm = np.zeros_like(pad)
    for i in range(0, len(pad) - n, hop):
        f = np.fft.rfft(pad[i:i + n] * win)
        f = np.abs(f) * np.exp(1j * rng.uniform(-np.pi, np.pi, f.shape))
        y[i:i + n] += np.fft.irfft(f).astype(np.float32) * win
        norm[i:i + n] += win ** 2
    y = y / np.maximum(norm, 1e-3)
    y = y[n:n + len(x)]
    y = y / (np.abs(y).max() + 1e-9) * 0.8 + 0.22 * x / (np.abs(x).max() + 1e-9)
    return (y / np.abs(y).max() * 0.75).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--rhv", required=True)
    ap.add_argument("--voice", default="volodymyr")
    ap.add_argument("--rate", default="97")
    ap.add_argument("--pitch", default="92")
    a = ap.parse_args()
    exe = os.path.join(a.rhv, "usr/bin/RHVoice-test")
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(a.rhv, "usr/lib/x86_64-linux-gnu"))
    tmp = tempfile.mkdtemp()
    beats = [l.strip() for l in open(a.script, encoding="utf-8") if l.strip()]
    audio, words, t = [np.zeros(int(0.5 * SR), np.float32)], [], 0.5
    for bi, line in enumerate(beats):
        pre = PAUSE_BEFORE.get(bi, 0.0)
        if pre:
            audio.append(np.zeros(int(pre * SR), np.float32))
            t += pre
        for si, sent in enumerate(sentences(line)):
            spoken = sent.replace("«", "").replace("»", "").replace("…", ".")
            p = os.path.join(tmp, f"b{bi}_{si}.wav")
            rate = "88" if bi in WHISPER_BEATS else a.rate
            subprocess.run([exe, "-p", a.voice, "-r", rate, "-t", a.pitch, "-R", "24000", "-o", p],
                           input=spoken.encode(), env=env, check=True, cwd=a.rhv + "/..")
            x = trim(read_wav(p))
            if bi in WHISPER_BEATS:
                x = whisper(x)
            for w in word_times(sent, x):
                words.append({"w": w["w"], "s": round(t + w["s"], 3), "e": round(t + w["e"], 3), "beat": bi})
            audio.append(x)
            t += len(x) / SR
            gap = 0.34 if sent.endswith((".", "…", "!", "?", ".»")) else 0.25
            audio.append(np.zeros(int(gap * SR), np.float32))
            t += gap
        audio.append(np.zeros(int(0.25 * SR), np.float32))
        t += 0.25
    audio.append(np.zeros(int(1.5 * SR), np.float32))
    y = np.concatenate(audio)
    y = y / (np.abs(y).max() + 1e-9) * 0.89
    with wave.open(os.path.join(a.out, "voice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    json.dump(words, open(os.path.join(a.out, "words.json"), "w"), ensure_ascii=False, indent=0)
    print(f"voice.wav {len(y) / SR:.1f}s, {len(words)} words")


if __name__ == "__main__":
    main()
