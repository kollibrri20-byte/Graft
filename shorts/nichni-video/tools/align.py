"""Carry word timings from a reference narration onto another recording of the same text (DTW on log-mel).

  python tools/align.py ref.wav ref_words.json target_audio out_dir
    -> out_dir/voice.wav (target, 48 kHz mono) + out_dir/words.json (timings on the target)

Used to put the author's own ElevenLabs voiceover under a video that was first timed to a draft voice.
"""
import json
import os
import subprocess
import sys

import numba
import numpy as np

SR = 16000
HOP = 0.02


def load(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def logmel(x, n_mels=40):
    n_fft, hop = 512, int(SR * HOP)
    win = np.hanning(n_fft).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (n_fft // 2, n_fft // 2)), n_fft)[::hop] * win
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    imel = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = imel(np.linspace(mel(80), mel(7600), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / SR).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), np.float32)
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        fb[m - 1, a:b] = (np.arange(a, b) - a) / max(1, b - a)
        fb[m - 1, b:c] = (c - np.arange(b, c)) / max(1, c - b)
    f = np.log(spec @ fb.T + 1e-8)
    energy = f.mean(1)
    f = (f - f.mean(0)) / (f.std(0) + 1e-6)
    # add deltas (shape of the speech, speaker independent-ish)
    d = np.gradient(f, axis=0)
    return np.concatenate([f, 2 * d], 1).astype(np.float32), energy


@numba.njit(cache=True)
def dtw(A, B, band):
    n, m = A.shape[0], B.shape[0]
    D = np.full((n + 1, m + 1), np.inf, np.float32)
    D[0, 0] = 0
    for i in range(1, n + 1):
        jc = int(i * m / n)
        j0 = max(1, jc - band)
        j1 = min(m, jc + band)
        for j in range(j0, j1 + 1):
            c = 0.0
            for k in range(A.shape[1]):
                dd = A[i - 1, k] - B[j - 1, k]
                c += dd * dd
            c = np.sqrt(c)
            best = D[i - 1, j - 1]
            if D[i - 1, j] < best:
                best = D[i - 1, j] + 0.3 * c
            if D[i, j - 1] < best:
                best = D[i, j - 1] + 0.3 * c
            D[i, j] = c + best
    # backtrack
    i, j = n, m
    path = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        a, b, c = D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]
        if a <= b and a <= c:
            i -= 1
            j -= 1
        elif b <= c:
            i -= 1
        else:
            j -= 1
    return path[::-1]


def main():
    ref, ref_words, tgt, out = sys.argv[1:5]
    xr, xt = load(ref), load(tgt)
    A, er = logmel(xr)
    Bm, et = logmel(xt)
    print(f"ref {len(xr) / SR:.1f}s  target {len(xt) / SR:.1f}s  frames {len(A)}x{len(Bm)}")
    band = int(max(len(A), len(Bm)) * 0.25)
    path = dtw(A, Bm, band)
    r2t = np.zeros(len(A))
    cnt = np.zeros(len(A))
    for i, j in path:
        r2t[i] += j
        cnt[i] += 1
    r2t = r2t / np.maximum(cnt, 1) * HOP
    r2t = np.maximum.accumulate(r2t)

    def mp(t):
        k = min(len(r2t) - 1, max(0, int(round(t / HOP))))
        return float(r2t[k])

    words = json.load(open(ref_words))
    out_w = []
    for w in words:
        s, e = mp(w["s"]), mp(w["e"])
        out_w.append(dict(w, s=round(s, 3), e=round(max(e, s + 0.08), 3)))
    # snap word starts that sit inside target silence to its end (speech onset)
    thr = np.percentile(et, 30)
    for w in out_w:
        k = int(w["s"] / HOP)
        while k < len(et) - 1 and et[k] < thr and k * HOP < w["e"]:
            k += 1
        w["s"] = round(k * HOP, 3)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tgt, "-ac", "1", "-ar", "48000", os.path.join(out, "voice.wav")], check=True)
    json.dump(out_w, open(os.path.join(out, "words.json"), "w"), ensure_ascii=False, indent=0)
    print("words", len(out_w), "last", out_w[-1])


if __name__ == "__main__":
    main()
