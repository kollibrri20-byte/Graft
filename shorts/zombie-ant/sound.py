"""Procedural sound design for the zombie-ant short (no external services).

  python sound.py render.sfx.json sfx/ music.wav <seconds>
Writes one wav per distinct cue into sfx/ + manifest.json (same format as eleven.py sfx),
and a dark ambient music bed.
"""
import json
import os
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(4)


def bp(x, lo=None, hi=None, order=4):
    if lo and hi:
        s = butter(order, [lo, hi], "band", fs=SR, output="sos")
    elif lo:
        s = butter(order, lo, "high", fs=SR, output="sos")
    else:
        s = butter(order, hi, "low", fs=SR, output="sos")
    return sosfilt(s, x)


def env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def fade(x, fi=0.05, fo=0.3):
    n = len(x)
    e = np.ones(n)
    a, b = int(fi * SR), int(fo * SR)
    e[:a] = np.linspace(0, 1, a)
    e[n - b:] = np.linspace(1, 0, b)
    return x * e


def noise(n):
    return rng.standard_normal(n)


def clicks(sec, rate, lo, hi, dec=0.004, amp_var=0.6):
    n = int(sec * SR)
    x = np.zeros(n)
    t = 0.0
    while t < sec - 0.02:
        t += rng.exponential(1 / rate)
        i = int(t * SR)
        m = int(0.02 * SR)
        if i + m >= n:
            break
        x[i:i + m] += noise(m) * env(m, 0.0003, dec) * (1 - amp_var * rng.random())
    return bp(x, lo, hi)


def sparkle(sec, n_notes=14, base=1800):
    n = int(sec * SR)
    x = np.zeros(n)
    t = np.arange(n) / SR
    for k in range(n_notes):
        s = int(rng.uniform(0, sec * 0.8) * SR)
        m = min(n - s, int(0.6 * SR))
        f = base * 2 ** (rng.integers(0, 12) / 6)
        x[s:s + m] += np.sin(2 * np.pi * f * t[:m]) * env(m, 0.002, 0.15) * 0.3
    return x


def jungle(sec):
    n = int(sec * SR)
    t = np.arange(n) / SR
    bed = bp(noise(n), 300, 3000) * 0.08 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.13 * t))
    # cicada-like insects
    ins = np.zeros(n)
    for f, am, ph in ((4200, 0.05, 0), (5600, 0.03, 1.3), (3300, 0.03, 2.2)):
        mod = (0.5 + 0.5 * np.sin(2 * np.pi * (28 + 5 * rng.random()) * t)) ** 3
        swell = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + ph)
        ins += bp(noise(n), f * 0.9, f * 1.1) * mod * swell * am * 8
    # birds: chirps with pitch sweeps
    birds = np.zeros(n)
    for k in range(int(sec / 1.6)):
        s = int(rng.uniform(0, sec - 1) * SR)
        f0 = rng.uniform(1800, 3800)
        for j in range(rng.integers(1, 4)):
            m = int(0.12 * SR)
            s2 = s + j * int(0.16 * SR)
            if s2 + m >= n:
                break
            tt = np.arange(m) / SR
            f = f0 + rng.uniform(-900, 900) * tt / 0.12
            birds[s2:s2 + m] += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / 0.12) ** 2 * 0.12
    drip = np.zeros(n)
    for k in range(int(sec / 2)):
        s = int(rng.uniform(0, sec - 0.3) * SR)
        m = int(0.08 * SR)
        tt = np.arange(m) / SR
        drip[s:s + m] += np.sin(2 * np.pi * (900 + 1400 * tt / 0.08) * tt) * env(m, 0.001, 0.02) * 0.2
    return fade(bed + ins + bp(birds, 1200, 7000) + drip, 1.0, 1.5)


def make(kind, sec):
    n = int(sec * SR)
    t = np.arange(n) / SR
    if kind.startswith("ambience"):
        return jungle(sec)
    if kind.startswith("skitter"):
        x = clicks(sec, 55, 2500, 9000, 0.003) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
        return fade(x, 0.2, 0.6)
    if kind == "spore_land":
        x = np.sin(2 * np.pi * np.cumsum(700 + 500 * np.exp(-t * 25)) / SR) * env(n, 0.002, 0.08)
        return x + sparkle(sec, 6, 2600) * 0.6
    if kind == "whoosh":
        x = bp(noise(n), 200, 3000) * np.sin(np.pi * np.clip(t / sec, 0, 1)) ** 2
        sub = np.sin(2 * np.pi * np.cumsum(90 - 50 * t / sec) / SR) * np.sin(np.pi * t / sec) * 0.6
        return x + sub
    if kind in ("sprout", "grow", "spread"):
        # creaky, wet organic growth: low granular creaks + squelches
        creak = np.zeros(n)
        rate = {"sprout": 25, "grow": 35, "spread": 60}[kind]
        tt = 0.0
        while tt < sec - 0.1:
            tt += rng.exponential(1 / rate)
            i = int(tt * SR)
            m = int(0.05 * SR)
            if i + m >= n:
                break
            f = rng.uniform(120, 400)
            creak[i:i + m] += np.sin(2 * np.pi * f * np.arange(m) / SR) * env(m, 0.002, 0.02) * rng.random()
        wet = bp(noise(n), 150, 900) * (0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * t)) ** 4 * 0.6
        low = np.sin(2 * np.pi * 55 * t + 3 * np.sin(2 * np.pi * 0.7 * t)) * 0.25
        return fade(creak + wet + low, 0.2, 0.6)
    if kind == "twitch":
        x = clicks(sec, 30, 1500, 7000, 0.006, 0.2) + clicks(sec, 12, 300, 2000, 0.01) * 0.8
        return fade(x, 0.01, 0.2)
    if kind == "hit":
        f = 40 + 60 * np.exp(-t * 8)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.003, 0.9)
        x += bp(noise(n), 60, 400) * env(n, 0.002, 0.3) * 0.5
        drone = np.sin(2 * np.pi * 73.4 * t) * 0.3 + np.sin(2 * np.pi * 110 * t) * 0.15
        return x + drone * np.sin(np.pi * np.clip(t / sec, 0, 1))
    if kind == "bite":
        m = int(0.25 * SR)
        x = np.zeros(n)
        for k in range(3):
            s = int(k * 0.035 * SR)
            x[s:s + m] += bp(noise(m), 1500, 9000) * env(m, 0.0005, 0.03 - 0.007 * k)
        x += np.sin(2 * np.pi * np.cumsum(220 * np.exp(-t * 20) + 90) / SR) * env(n, 0.001, 0.05) * 0.6
        return x
    if kind == "death":
        f = 220 * 2 ** (-t / sec)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (sec * 0.5)) * 0.6
        x += bp(noise(n), 200, 1200) * np.exp(-t / 0.4) * 0.3
        return fade(x, 0.05, 0.6)
    if kind == "spores":
        puff = bp(noise(n), 300, 3000) * env(n, 0.01, 0.35)
        return fade(puff + sparkle(sec, 22, 2200), 0.01, 0.8)
    if kind == "stone":
        f = 45 + 50 * np.exp(-t * 12)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.7)
        x += bp(noise(n), 80, 1500) * env(n, 0.001, 0.12) * 0.8
        x += bp(noise(n), 2000, 8000) * env(n, 0.05, 0.6) * 0.05
        return x
    return noise(n) * env(n, 0.001, 0.05)


def write(path, x, stereo=False):
    x = x / (np.abs(x).max() + 1e-9) * 0.89
    if stereo and x.ndim == 1:
        x = np.stack([x, x], 1)
    x16 = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2 if x16.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(x16.tobytes())


def music(sec):
    """Dark, tense ambient bed: drone in D minor, slow heartbeat pulse, sparse eerie plucks."""
    n = int(sec * SR)
    t = np.arange(n) / SR
    L = np.zeros(n)
    R = np.zeros(n)
    for f, a, det in ((36.7, 0.35, 0.15), (73.4, 0.25, 0.3), (110.0, 0.12, 0.4), (87.3, 0.08, 0.5)):
        L += a * np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.05 * t))
        R += a * np.sin(2 * np.pi * (f + det) * t)
    pad = bp(noise(n), 200, 900) * 0.04 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.03 * t))
    L += pad
    R += bp(noise(n), 200, 900) * 0.04
    # heartbeat pulse that speeds up a little through the story
    beat = np.zeros(n)
    tt = 1.0
    while tt < sec - 2:
        bpm = 52 + 18 * tt / sec
        for off, amp in ((0, 1.0), (0.22, 0.6)):
            i = int((tt + off) * SR)
            m = int(0.3 * SR)
            if i + m < n:
                k = np.arange(m) / SR
                beat[i:i + m] += amp * np.sin(2 * np.pi * (48 + 30 * np.exp(-k * 30)) * k) * np.exp(-k / 0.09)
        tt += 60 / bpm
    L += beat * 0.45
    R += beat * 0.45
    # eerie plucks (D minor pentatonic, high, sparse)
    notes = [293.7, 349.2, 392.0, 440.0, 523.3, 587.3]
    tt = 2.0
    while tt < sec - 3:
        f = notes[rng.integers(0, len(notes))]
        i = int(tt * SR)
        m = int(2.5 * SR)
        if i + m < n:
            k = np.arange(m) / SR
            p = (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(4 * np.pi * f * k)) * np.exp(-k / 0.7) * 0.12
            pan = rng.random()
            L[i:i + m] += p * (1 - pan)
            R[i:i + m] += p * pan
            # echo
            j = i + int(0.42 * SR)
            if j + m < n:
                L[j:j + m] += p * 0.35 * pan
                R[j:j + m] += p * 0.35 * (1 - pan)
        tt += rng.uniform(1.6, 3.4)
    x = np.stack([L, R], 1)
    e = np.ones(n)
    e[:int(2 * SR)] = np.linspace(0, 1, int(2 * SR))
    e[-int(3 * SR):] = np.linspace(1, 0, int(3 * SR))
    return x * e[:, None]


def main():
    cues = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    man = {}
    for c in cues:
        k = c.get("prompt") or c["sfx"]
        if k in man:
            continue
        name = f"{c['sfx']}_{len(man):02d}.wav"
        write(os.path.join(out, name), make(c["sfx"], float(c.get("seconds", 1.2))))
        man[k] = name
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1, ensure_ascii=False)
    print(len(man), "sounds")
    write(sys.argv[3], music(float(sys.argv[4])), stereo=True)
    print("music", sys.argv[3])


main()
