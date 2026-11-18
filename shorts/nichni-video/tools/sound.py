"""Procedural sound for «Нічні відео» (no downloads, no licences needed).

  python tools/sound.py <project dir>
    -> sfx/*.wav + sfx/manifest.json  (one sound per cue prompt in render.sfx.json, used by assemble.py --sfx-lib)
    -> bed.wav                         (drone score + ambiences + breathing + heartbeat, timed by shots.json/beats.json)
"""
import json
import os
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
proj = os.path.abspath(sys.argv[1])
rng = np.random.default_rng(11)


def bp(x, lo=None, hi=None, order=2):
    if lo and hi:
        sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    elif lo:
        sos = butter(order, lo, btype="high", fs=SR, output="sos")
    else:
        sos = butter(order, hi, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x)


def T(sec):
    return np.arange(int(sec * SR)) / SR


def env(n, a, d, sustain=0.0):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * (sustain + (1 - sustain) * np.exp(-t / max(d, 1e-4)))


def noise(n):
    return rng.standard_normal(n)


def norm(x, peak=0.9):
    return x / (np.abs(x).max() + 1e-9) * peak


def write(path, x):
    x = np.asarray(x, np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def sine(f, t):
    return np.sin(2 * np.pi * np.cumsum(np.broadcast_to(f, t.shape)) / SR)


# ---------------------------------------------------------------- one-shots
def s_tap():
    n = int(0.12 * SR)
    return norm(bp(noise(n), 1500, 6000) * env(n, 0.0005, 0.008) + 0.4 * sine(1800, T(0.12)) * env(n, 0.0005, 0.01), 0.6)


def s_buzz():
    t = T(0.75)
    gate = ((t > 0.02) & (t < 0.30)) | ((t > 0.42) & (t < 0.70))
    x = np.sign(np.sin(2 * np.pi * 165 * t)) * 0.5 + np.sin(2 * np.pi * 330 * t)
    x = bp(x, 120, 2500) * gate * (0.8 + 0.2 * np.sin(2 * np.pi * 23 * t))
    return norm(bp(x, hi=4000) + 0.3 * bp(noise(len(t)), 100, 400) * gate, 0.7)


def s_boom(sec=3.5, f0=70, f1=32):
    t = T(sec)
    f = f1 + (f0 - f1) * np.exp(-t * 3)
    x = sine(f, t) * env(len(t), 0.004, 1.2)
    x += 0.5 * bp(noise(len(t)), hi=180) * env(len(t), 0.002, 0.5)
    x += 0.15 * bp(noise(len(t)), 800, 4000) * env(len(t), 0.001, 0.05)
    return norm(x, 0.95)


def s_lock():
    t = T(0.45)
    n = len(t)
    x = np.zeros(n)
    for off, g in ((0.0, 0.6), (0.07, 1.0)):
        s = int(off * SR)
        m = n - s
        tt = np.arange(m) / SR
        click = bp(noise(m), 2000, 9000) * np.exp(-tt / 0.004)
        ring = (np.sin(2 * np.pi * 2650 * tt) + 0.6 * np.sin(2 * np.pi * 4170 * tt) + 0.4 * np.sin(2 * np.pi * 1210 * tt)) * np.exp(-tt / 0.05)
        thunk = np.sin(2 * np.pi * 180 * tt) * np.exp(-tt / 0.03)
        x[s:] += g * (click + 0.25 * ring + 0.5 * thunk)
    return norm(x, 0.8)


def s_place():
    t = T(0.6)
    x = sine(90 + 60 * np.exp(-t * 40), t) * env(len(t), 0.001, 0.06)
    x += 0.5 * bp(noise(len(t)), 800, 5000) * env(len(t), 0.001, 0.02)
    s = int(0.11 * SR)
    x[s:] += 0.35 * bp(noise(len(t) - s), 1500, 7000) * env(len(t) - s, 0.001, 0.012)
    return norm(x, 0.8)


def s_beep():
    t = T(0.5)
    g = ((t > 0.0) & (t < 0.09)) | ((t > 0.17) & (t < 0.26))
    return norm(np.sin(2 * np.pi * 2350 * t) * g * 0.7, 0.45)


def s_sheets():
    t = T(1.8)
    e = np.clip(np.sin(np.pi * t / 1.8), 0, 1) ** 1.5 * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 2.3 * t)))
    flutter = 0.5 + 0.5 * np.clip(bp(noise(len(t)), hi=30) * 8, -1, 1)
    return norm(bp(noise(len(t)), 900, 7000) * e * flutter, 0.6)


def s_creak():
    t = T(1.3)
    n = len(t)
    x = np.zeros(n)
    rate = 55 + 30 * np.sin(2 * np.pi * 0.6 * t) + 15 * np.sin(2 * np.pi * 2.1 * t)
    ph = np.cumsum(rate) / SR
    pulses = np.where(np.diff(np.floor(ph), prepend=0) > 0)[0]
    for p in pulses:
        x[p] += 1 + 0.4 * rng.random()
    y = bp(x, 380, 520, order=3) + 0.6 * bp(x, 900, 1100, order=3) + 0.3 * bp(x, 1700, 1900, order=3)
    return norm(y * np.clip(np.sin(np.pi * t / 1.3), 0, 1), 0.7)


def s_camstart():
    t = T(0.35)
    f = np.where(t < 0.12, 1320, 1760)
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.003, 0.12) * (t < 0.3), 0.4)


def s_sting(sec=3.2, loud=False):
    t = T(sec)
    x = np.zeros(len(t))
    freqs = [233.1, 246.9, 261.6, 277.2, 466.2, 493.9, 987.8] if not loud else [110, 116.5, 155.6, 164.8, 220, 233.1, 311.1, 329.6, 659.3, 698.5]
    for k, f in enumerate(freqs):
        vib = 1 + 0.004 * np.sin(2 * np.pi * (5.5 + k * 0.37) * t)
        saw = (2 * ((np.cumsum(f * vib) / SR) % 1) - 1)
        x += saw * (0.6 + 0.4 * np.sin(2 * np.pi * (7 + k) * t))  # tremolo
    x = bp(x, 150, 5000)
    if loud:
        e = env(len(t), 0.005, 1.4)
        x = x * e + s_boom(sec, 80, 30)[: len(t)] * 1.2 + bp(noise(len(t)), 300, 6000) * env(len(t), 0.002, 0.15)
    else:
        e = np.minimum(1, t / 1.2) ** 2 * np.exp(-np.maximum(0, t - 1.6) / 0.6)
        x = x * e
    return norm(x, 0.9)


def s_step():
    t = T(0.3)
    return norm(sine(70, t) * env(len(t), 0.003, 0.04) + 0.4 * bp(noise(len(t)), 300, 2000) * env(len(t), 0.002, 0.03), 0.5)


LIB = {
    "phone tap": s_tap, "phone buzz": s_buzz, "low hit": lambda: s_boom(3.0), "deep boom": lambda: s_boom(4.0, 60, 28),
    "low boom": lambda: s_boom(3.5, 65, 30), "deadbolt lock click": s_lock, "plastic camcorder set down on wood": s_place,
    "camcorder record beep": s_beep, "bed sheets rustle": s_sheets, "old bed creak": s_creak,
    "phone camera start sound": s_camstart, "creepy string sting": s_sting, "horror sting eyes open": lambda: s_sting(4.0, True),
    "step": s_step,
}

# ---------------------------------------------------------------- beds
def breath(sec, period, depth=1.0, fast=False):
    """Breathing: noise through a mouth/nose formant, inhale + exhale per cycle (jittered)."""
    n = int(sec * SR)
    out = np.zeros(n)
    t0 = 0.0
    while t0 < sec:
        p = period * (0.75 + 0.5 * rng.random()) if fast else period * (0.95 + 0.1 * rng.random())
        for part, (start, dur, lo, hi, g) in enumerate(((0, 0.42 * p, 700, 2600, 0.6), (0.48 * p, 0.5 * p, 350, 1700, 1.0))):
            s = int((t0 + start) * SR)
            m = int(dur * SR)
            if s + m >= n:
                break
            tt = np.linspace(0, 1, m)
            e = np.sin(np.pi * tt) ** (1.2 if part else 2.0) * (0.7 + 0.6 * rng.random())
            out[s:s + m] += bp(noise(m), lo, hi) * e * g * depth
        t0 += p
    return out


def giggles(sec, at):
    """Stifled laughter: bursts of short nasal puffs."""
    n = int(sec * SR)
    out = np.zeros(n)
    for a in at:
        k = rng.integers(4, 7)
        for j in range(k):
            s = int((a + j * (0.085 + 0.02 * rng.random())) * SR)
            m = int(0.06 * SR)
            if s + m < n:
                out[s:s + m] += bp(noise(m), 600, 3000) * np.sin(np.linspace(0, np.pi, m)) ** 2 * (1 - j / (k + 2))
                out[s:s + m] += 0.3 * np.sin(2 * np.pi * (180 + 20 * j) * np.arange(m) / SR) * np.sin(np.linspace(0, np.pi, m))
    return out


def heartbeat(sec, bpm0, bpm1):
    n = int(sec * SR)
    out = np.zeros(n)
    t = 0.0
    while t < sec - 0.4:
        bpm = bpm0 + (bpm1 - bpm0) * t / sec
        for off, g in ((0, 1.0), (0.23, 0.7)):
            s = int((t + off) * SR)
            m = int(0.25 * SR)
            if s + m < n:
                tt = np.arange(m) / SR
                out[s:s + m] += g * np.sin(2 * np.pi * (48 + 30 * np.exp(-tt * 30)) * tt) * np.exp(-tt / 0.07)
        t += 60 / bpm
    return out


def ticks(sec):
    n = int(sec * SR)
    out = np.zeros(n)
    for k in range(int(sec)):
        s = int(k * SR)
        m = int(0.03 * SR)
        if s + m < n:
            out[s:s + m] += bp(noise(m), 2500 if k % 2 else 3300, 6000) * np.exp(-np.arange(m) / SR / 0.004)
    return out


def main():
    os.makedirs(os.path.join(proj, "sfx"), exist_ok=True)
    cues = json.load(open(os.path.join(proj, "render.sfx.json")))
    man = {}
    for c in cues:
        k = c.get("prompt") or c["sfx"]
        if k in man:
            continue
        fn = LIB.get(k) or LIB.get(c["sfx"]) or s_tap
        name = "".join(ch if ch.isalnum() else "_" for ch in k)[:40] + ".wav"
        write(os.path.join(proj, "sfx", name), fn())
        man[k] = name
    json.dump(man, open(os.path.join(proj, "sfx", "manifest.json"), "w"), indent=1)
    print("sfx:", len(man))

    meta = json.load(open(os.path.join(proj, "shots.json")))
    fps = meta["fps"]
    dur = meta["end"] / fps + 4
    n = int(dur * SR)
    t = np.arange(n) / SR
    L = np.zeros(n)
    Rr = np.zeros(n)
    beats = json.load(open(os.path.join(proj, "beats.json")))
    bt = lambda i: beats[i]["s"]

    def add(x, start, gain=1.0, pan=0.0):
        s = int(start * SR)
        x = x[: max(0, n - s)]
        L[s:s + len(x)] += x * gain * (1 - max(0, pan))
        Rr[s:s + len(x)] += x * gain * (1 + min(0, pan))

    # level of the score per shot look
    lvl = np.zeros(n)
    LV = {"clean": 0.55, "phone": 0.8, "cam": 0.9, "rew": 0.7, "glitch": 0.25, "flash": 0.9, "selfie": 0.6, "black": 0.0}
    for s_ in meta["shots"]:
        a, b = int((s_["f0"] - 1) / fps * SR), int(s_["f1"] / fps * SR)
        lvl[a:b] = LV.get(s_["fx"], 0.6)
        if s_["name"].startswith("m_"):
            lvl[a:b] = 0.3
    lvl = np.convolve(lvl, np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
    # tension rises through the tape
    rise = np.clip((t - bt(10)) / (bt(15) - bt(10)), 0, 1) * (t < bt(16))
    # drone: low A with a beating minor second + slowly moving filtered pad
    drone = 0.5 * np.sin(2 * np.pi * 55 * t) + 0.35 * np.sin(2 * np.pi * 58.27 * t + 1) + 0.25 * np.sin(2 * np.pi * 82.4 * t)
    drone *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t)
    pad = np.zeros(n)
    for f, ph in ((110, 0), (130.8, 1.3), (164.8, 2.1), (155.6, 0.4)):
        pad += (2 * ((f * t + ph) % 1) - 1) * (0.5 + 0.5 * np.sin(2 * np.pi * (0.05 + f / 4000) * t + ph))
    pad = bp(pad, hi=700) * 0.25
    high = np.sin(2 * np.pi * 1760 * t) * 0.02 * rise + np.sin(2 * np.pi * 1864.7 * t) * 0.02 * rise
    score = (drone * 0.55 + pad * (0.6 + 0.8 * rise) + high) * lvl
    air = bp(noise(n), 80, 900) * 0.05 * lvl
    L += score + air
    Rr += score * 0.97 + bp(noise(n), 80, 900) * 0.05 * lvl
    # tape hiss + hum during the camcorder tape; rewind whine
    for s_ in meta["shots"]:
        a, b = (s_["f0"] - 1) / fps, s_["f1"] / fps
        m = int((b - a) * SR)
        if s_["fx"] in ("cam", "rew", "glitch"):
            hiss = bp(noise(m), 3000, 12000) * 0.035 + np.sin(2 * np.pi * 50 * np.arange(m) / SR) * 0.02
            add(hiss, a)
        if s_["fx"] == "rew":
            tt = np.arange(m) / SR
            whine = np.sin(2 * np.pi * np.cumsum(900 + 1400 * tt / tt[-1]) / SR) * 0.05 + bp(noise(m), 200, 2000) * 0.1 * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 13 * tt)))
            add(whine, a)
        if s_["fx"] == "phone":
            add(bp(noise(m), 200, 6000) * 0.012, a)
    # beat 5-6: the breathing of whoever was filming (close, fast) and the sleeper's calm breathing
    sh = {s_["name"]: s_ for s_ in meta["shots"]}
    a = (sh["p_face"]["f0"] - 1) / fps
    b = sh["p_face2"]["f1"] / fps
    add(breath(b - a, 0.62, fast=True), a, 0.16, pan=0.15)
    add(giggles(b - a, [x - a for x in (bt(6) + 4.0, bt(6) + 6.2, bt(6) + 8.1)]), a, 0.20, pan=-0.1)
    add(breath(b - a, 4.2), a, 0.05, pan=-0.3)
    # sleeper's slow breathing whenever we watch him at night
    for nm in ("p_door", "p_mid", "p_bed", "c_bed", "h_door", "a_face"):
        s_ = sh[nm]
        add(breath((s_["f1"] - s_["f0"]) / fps, 4.2), (s_["f0"] - 1) / fps, 0.06)
    # clock ticking in the night / evening rooms
    for nm in ("e_wide", "e_locks", "e_door", "n_ward", "n_cc", "h_door", "a_face", "l_front", "l_hands", "l_face", "l_bed"):
        s_ = sh[nm]
        add(ticks((s_["f1"] - s_["f0"] + 1) / fps), (s_["f0"] - 1) / fps, 0.05, pan=0.3)
    # heartbeat in front of the screen, speeding up
    a = (sh["l_front"]["f0"] - 1) / fps
    b = sh["l_bed"]["f1"] / fps
    add(heartbeat(b - a, 72, 118), a, 0.28)
    # memory shot: a reversed swell into it
    a = (sh["f_low"]["f0"] - 1) / fps
    sw = bp(noise(int(2.0 * SR)), 300, 4000) * np.linspace(0, 1, int(2.0 * SR)) ** 3
    add(sw, a - 2.0, 0.12)
    # silence after the final sting
    end_f = (sh["black"]["f0"]) / fps
    fade = np.clip(1 - (t - end_f) / 2.5, 0, 1)
    L *= fade
    Rr *= fade
    x = np.stack([L, Rr], 1)
    x = x / (np.abs(x).max() + 1e-9) * 0.8
    write(os.path.join(proj, "bed.wav"), x)
    print(f"bed.wav {dur:.1f}s")


if __name__ == "__main__":
    main()
