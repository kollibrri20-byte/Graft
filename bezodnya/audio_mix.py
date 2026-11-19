"""Процедурна музика (темний ембієнт: дроуни + рідкісне піаніно), звукові ефекти й фінальне зведення.

    python audio_mix.py OUT_DIR      # потрібні OUT_DIR/timeline.json і OUT_DIR/voice.wav
Результат: OUT_DIR/mix.wav (48 кГц, стерео).
"""
import json
import math
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, oaconvolve, sosfilt, sosfiltfilt

SR = 48000
rng = np.random.default_rng(2026)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def env_adsr(n, a, r):
    e = np.ones(n, np.float32)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def reverb_ir(sec=3.5, damp=3000, seed=1):
    r = np.random.default_rng(seed)
    n = int(sec * SR)
    t = np.arange(n) / SR
    irs = []
    for ch in range(2):
        w = r.standard_normal(n) * np.exp(-t * 6.9 / sec)
        w = lp(w, damp)
        w[: int(0.012 * SR)] = 0
        irs.append(w / np.sqrt((w ** 2).sum()))
    return irs


IR_BIG = reverb_ir(4.5, 2500, 1)
IR_MID = reverb_ir(1.8, 4000, 2)


def verb(x, ir, wet=0.4):
    """x: моно або (2, n) -> стерео (2, n)."""
    if x.ndim == 1:
        x = np.stack([x, x])
    out = np.zeros_like(x)
    for c in range(2):
        out[c] = x[c] * (1 - wet) + oaconvolve(x[c], ir[c])[: x.shape[1]] * wet
    return out


# ============================================================ музика
def music(total, tl):
    n = int(total * SR)
    t = np.arange(n, dtype=np.float64) / SR
    depth_of = np.zeros(n, np.float32)  # 0..1, наскільки "глибоко" — керує напругою
    for k, s in enumerate(tl):
        a, b = int(s["start"] * SR), int((s["start"] + s["dur"]) * SR)
        d0 = max(0, (k - 3) / 28)
        depth_of[a:b] = np.linspace(d0, max(0, (k - 2) / 28), b - a)
    depth_of[: int(tl[3]["start"] * SR)] = 0.75  # хук — напружено
    depth_of = np.clip(depth_of, 0, 1)
    out = np.zeros((2, n), np.float32)
    # дроун: A1 + E2 + легкий биттінг
    root = 55.0
    for f, a, det in ((root, 0.32, 0.12), (root * 1.5, 0.16, 0.09), (root * 2, 0.10, 0.15), (root * 0.5, 0.25, 0.05)):
        for ch, sgn in ((0, -1), (1, 1)):
            ph = 2 * np.pi * (f + sgn * det) * t
            w = np.sin(ph) + 0.3 * np.sin(2 * ph + 0.3) + 0.12 * np.sin(3 * ph)
            lfo = 0.65 + 0.35 * np.sin(2 * np.pi * t / (23 + f % 7) + f)
            out[ch] += (w * a * lfo).astype(np.float32)
    # напруга: дисонансний кластер (мала секунда/тритон) наростає з глибиною
    for f, a in ((root * 2 * 2 ** (1 / 12), 0.09), (root * 2 * 2 ** (6 / 12), 0.07), (root * 4 * 2 ** (1 / 12), 0.03)):
        for ch in range(2):
            w = np.sin(2 * np.pi * (f + 0.2 * ch) * t + ch)
            out[ch] += (w * a * depth_of ** 1.5 * (0.6 + 0.4 * np.sin(2 * np.pi * t / 17))).astype(np.float32)
    # "океанський" гул — фільтрований шум
    for ch in range(2):
        nz = rng.standard_normal(n).astype(np.float32)
        out[ch] += lp(nz, 180, 4).astype(np.float32) * 0.5
    # рідкісне піаніно (ля мінор / фрігійський)
    notes = [57, 60, 64, 65, 69, 70, 72, 76, 52, 64]
    tp = 4.0
    while tp < total - 6:
        midi = notes[rng.integers(len(notes))]
        if rng.random() < 0.3:
            midi -= 12
        f = 440 * 2 ** ((midi - 69) / 12)
        dur = 6.0
        m = int(dur * SR)
        tt = np.arange(m) / SR
        w = np.zeros(m)
        for h, (amp, dec) in enumerate(((1, 1.6), (0.45, 1.0), (0.22, 0.7), (0.12, 0.5), (0.06, 0.35)), 1):
            w += amp * np.sin(2 * np.pi * f * h * (1 + 0.0004 * h * h) * tt) * np.exp(-tt / dec)
        w *= env_adsr(m, 0.004, 0.5) * 0.11
        i = int(tp * SR)
        pan = rng.uniform(0.3, 0.7)
        seg = slice(i, min(i + m, n))
        L = seg.stop - seg.start
        out[0, seg] += (w[:L] * (1 - pan)).astype(np.float32)
        out[1, seg] += (w[:L] * pan).astype(np.float32)
        tp += rng.uniform(5.5, 11.0) * (1.25 - 0.4 * float(depth_of[min(i, n - 1)]))
    # світліша "ракушкова" підкладка для рифу (сцена 8) і поверхні (4)
    for k in (3, 7):
        s = tl[k]
        a, b = int(s["start"] * SR), int((s["start"] + s["dur"]) * SR)
        tt = np.arange(b - a) / SR
        e = np.sin(np.pi * tt / tt[-1]) ** 2
        for f in (440, 554.4, 659.3, 880):
            for ch in range(2):
                out[ch, a:b] += (np.sin(2 * np.pi * (f + ch * 0.7) * tt) * 0.025 * e).astype(np.float32)
    out = verb(out, IR_BIG, 0.45)
    out = np.stack([hp(c, 30) for c in out]).astype(np.float32)
    out /= np.abs(out).max() + 1e-9
    # фінал: після сцени 32 залишаємо майже тишу
    s = tl[-1]
    a = int((s["start"] + s["dur"] * 0.62) * SR)
    fade = np.ones(n, np.float32)
    fade[a:] = np.linspace(1, 0.15, n - a)
    fade[int((s["start"] + s["dur"] * 0.84) * SR):] = 0.0
    return out * fade


# ============================================================ звукові ефекти
def noise(sec):
    return rng.standard_normal(int(sec * SR)).astype(np.float64)


def sfx_creak(sec=1.6, f0=180):
    n = int(sec * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.35 * np.sin(2 * np.pi * 0.7 * t) + 0.2 * rng.standard_normal() * t)
    ph = np.cumsum(2 * np.pi * f / SR)
    pulses = (np.sin(ph) > 0.97).astype(float)
    x = bp(pulses + 0.05 * rng.standard_normal(n), 120, 2500)
    x = sosfilt(butter(2, [f0 * 1.8, f0 * 2.4], "band", fs=SR, output="sos"), x) * 6 + x
    return x * env_adsr(n, 0.2, 0.5) * 0.5


def sfx_crack():
    n = int(2.5 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t * 25)
    x += 0.6 * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 4)
    for k in range(25):
        i = int((0.005 + rng.exponential(0.12)) * SR)
        if i < n - 200:
            x[i:i + 200] += rng.standard_normal(200) * np.exp(-np.arange(200) / 40) * rng.uniform(0.2, 0.8)
    x = hp(x, 60)
    return x / np.abs(x).max()


def sfx_breath(sec=3.5):
    n = int(sec * SR)
    t = np.arange(n) / SR
    e = np.clip(np.sin(2 * np.pi * t / 3.2), 0, 1) ** 2
    return bp(rng.standard_normal(n), 300, 1800) * e * 0.12


def sfx_waves(sec):
    n = int(sec * SR)
    t = np.arange(n) / SR
    x = lp(rng.standard_normal(n), 900) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 5.5) ** 2)
    x += hp(rng.standard_normal(n), 3000) * 0.08 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 5.5 + 1))
    return x * 0.35


def sfx_splash():
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t * 3)
    x = lp(x, 6000) * (1 - np.exp(-t * 40))
    bub = np.zeros(n)
    for _ in range(60):
        i = int(rng.uniform(0.1, 1.8) * SR)
        f = rng.uniform(300, 1200)
        m = int(0.06 * SR)
        tt = np.arange(m) / SR
        if i + m < n:
            bub[i:i + m] += np.sin(2 * np.pi * f * (1 + 4 * tt) * tt) * np.exp(-tt * 60) * 0.3
    return (x * 0.6 + bub) * 0.8


def sfx_crunch():
    n = int(1.2 * SR)
    x = np.zeros(n)
    for _ in range(120):
        i = int(abs(rng.normal(0.08, 0.08)) * SR)
        m = int(rng.uniform(0.002, 0.01) * SR)
        if i + m < n:
            x[i:i + m] += rng.standard_normal(m) * rng.uniform(0.2, 1)
    x = bp(x, 800, 7000)
    t = np.arange(n) / SR
    x += 0.5 * np.sin(2 * np.pi * 90 * t) * np.exp(-t * 12)
    return x / np.abs(x).max() * 0.8


def sfx_thud(f=45, dec=4.0, amp=1.0):
    n = int(3 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t * (1 - 0.15 * t / 3)) * np.exp(-t * dec)
    x += lp(rng.standard_normal(n), 200) * np.exp(-t * 15) * 0.6
    return x * amp


def sfx_clicks(sec, rate=2.0):
    n = int(sec * SR)
    x = np.zeros(n)
    tp = 0.0
    while tp < sec - 0.05:
        i = int(tp * SR)
        m = int(0.004 * SR)
        x[i:i + m] += np.sin(2 * np.pi * 3500 * np.arange(m) / SR) * np.exp(-np.arange(m) / 40)
        tp += rng.uniform(0.5, 1.2) / rate
    return bp(x, 1500, 9000) * 0.9


def sfx_bloop():
    n = int(5 * SR)
    t = np.arange(n) / SR
    f = 28 + 55 * (t / 5) ** 1.5
    ph = np.cumsum(2 * np.pi * f / SR)
    x = np.sin(ph) * env_adsr(n, 0.6, 1.8) + 0.4 * np.sin(2 * ph) * env_adsr(n, 0.8, 2.0)
    return x * 0.9


def sfx_hum(sec, f=95):
    n = int(sec * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2 * f * t) + 0.2 * lp(rng.standard_normal(n), 400)
    return x * env_adsr(n, 1.0, 1.5) * 0.12


def sfx_rumble(sec, amp=0.6):
    n = int(sec * SR)
    return lp(rng.standard_normal(n), 120, 4) * env_adsr(n, 0.8, 1.5) * amp * 3


def sfx_ice(sec):
    n = int(sec * SR)
    x = sfx_rumble(sec, 0.5)
    for _ in range(int(sec * 2)):
        i = int(rng.uniform(0, sec - 1) * SR)
        c = sfx_crack()[: int(0.8 * SR)] * rng.uniform(0.15, 0.4)
        c = lp(c, 2500)
        x[i:i + len(c)] += c[: n - i]
    return x


def sfx_wind(sec):
    n = int(sec * SR)
    t = np.arange(n) / SR
    return bp(rng.standard_normal(n), 300, 1500) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 7)) * 0.15


def sfx_whoosh(sec=3.0):
    n = int(sec * SR)
    t = np.arange(n) / SR
    e = np.sin(np.pi * t / sec) ** 2
    return lp(rng.standard_normal(n), 500) * e * 0.8


def place(buf, x, at, gain=1.0, pan=0.5, rv=None, wet=0.35):
    i = int(at * SR)
    if i >= buf.shape[1] or len(x) == 0:
        return
    x = x * gain
    if rv is not None:
        tail = np.zeros(len(x) + int(2.0 * SR))
        tail[: len(x)] = x
        st = verb(tail, rv, wet)
    else:
        st = np.stack([x * (1 - pan) * 2 ** 0.5, x * pan * 2 ** 0.5])
    m = min(st.shape[1], buf.shape[1] - i)
    buf[:, i:i + m] += st[:, :m]


def effects(total, tl):
    n = int(total * SR)
    fx = np.zeros((2, n))
    S = {s["scene"]: s for s in tl}

    def at(sc, u):
        return S[sc]["start"] + S[sc]["dur"] * u

    def dur(sc):
        return S[sc]["dur"]

    # 1–3: метал, дихання, тріск
    place(fx, sfx_breath(dur(1)), at(1, 0.0), 0.8, rv=IR_MID, wet=0.2)
    place(fx, sfx_creak(2.0, 160), at(1, 0.35), 0.7, 0.35, rv=IR_MID)
    place(fx, sfx_crack(), at(2, 0.1), 1.0, rv=IR_MID, wet=0.4)
    place(fx, sfx_thud(38, 2.5, 1.0), at(2, 0.1), 0.8, rv=IR_MID)
    place(fx, sfx_creak(3.0, 120), at(2, 0.25), 0.8, 0.6, rv=IR_MID)
    place(fx, sfx_crack()[: int(1.2 * SR)] * 0.5, at(2, 0.58), 0.6, rv=IR_MID)
    place(fx, sfx_breath(dur(2)), at(2, 0.3), 1.0, rv=IR_MID, wet=0.2)
    place(fx, sfx_creak(2.5, 200), at(3, 0.3), 0.5, 0.7, rv=IR_BIG)
    place(fx, sfx_rumble(dur(3), 0.4), at(3, 0.0), 1.0)
    # 4: хвилі, занурення
    place(fx, sfx_waves(dur(4) * 0.66), at(4, 0.0), 1.0, rv=IR_MID, wet=0.15)
    place(fx, sfx_splash(), at(4, 0.62), 1.0, rv=IR_MID, wet=0.25)
    place(fx, sfx_rumble(dur(4) * 0.36, 0.3), at(4, 0.64), 1.0)
    # 6: бляшанка
    place(fx, sfx_crunch(), at(6, 0.5), 1.0, rv=IR_MID, wet=0.4)
    # 7: прожектори
    place(fx, sfx_thud(120, 25, 0.5), at(7, 0.18), 1.0, rv=IR_MID)
    place(fx, sfx_hum(dur(7) * 0.8, 92), at(7, 0.18), 1.0)
    # 12–13: кашалот
    place(fx, sfx_clicks(dur(12), 1.6), at(12, 0.0), 0.5, 0.4, rv=IR_BIG, wet=0.5)
    place(fx, sfx_clicks(dur(13), 2.5), at(13, 0.0), 0.5, 0.6, rv=IR_BIG, wet=0.5)
    for u in (0.15, 0.42, 0.7):
        place(fx, sfx_thud(40, 3, 0.8), at(13, u), 1.0, rv=IR_BIG, wet=0.4)
    # 18: "Блуп"
    place(fx, sfx_bloop(), at(18, 0.12), 0.9, rv=IR_BIG, wet=0.55)
    place(fx, sfx_bloop(), at(18, 0.62), 0.6, rv=IR_BIG, wet=0.6)
    # 19: лід
    place(fx, sfx_ice(dur(19)), at(19, 0.0), 0.8, rv=IR_BIG, wet=0.4)
    # 20: ущелина — глухий гул
    place(fx, sfx_rumble(dur(20), 0.5), at(20, 0.0), 1.0)
    place(fx, sfx_creak(3, 90), at(20, 0.5), 0.3, rv=IR_BIG, wet=0.6)
    # 23: архівна палуба
    place(fx, sfx_wind(dur(23)), at(23, 0.0), 1.0)
    place(fx, sfx_waves(dur(23)), at(23, 0.0), 0.7)
    # 24–25: тиск, тріск
    place(fx, sfx_creak(3, 140), at(24, 0.4), 0.5, rv=IR_MID)
    place(fx, sfx_crack(), at(25, 0.13), 1.0, rv=IR_MID, wet=0.4)
    place(fx, sfx_thud(36, 2.5, 1.0), at(25, 0.13), 0.8, rv=IR_MID)
    place(fx, sfx_breath(4), at(25, 0.3), 1.0, rv=IR_MID, wet=0.2)
    # 26: посадка
    place(fx, sfx_thud(50, 6, 0.7), at(26, 0.42), 1.0, rv=IR_MID)
    place(fx, sfx_whoosh(4), at(26, 0.42), 0.8, rv=IR_BIG)
    # 28–29: двигуни, посадка
    place(fx, sfx_hum(dur(28) * 0.9, 80), at(28, 0.02), 0.8)
    place(fx, sfx_hum(dur(29) * 0.9, 105), at(29, 0.0), 0.8)
    place(fx, sfx_thud(55, 6, 0.5), at(29, 0.35), 1.0, rv=IR_MID)
    # 32: хвилі, занурення, тиша, один глухий удар
    place(fx, sfx_waves(dur(32) * 0.42), at(32, 0.0), 0.8, rv=IR_MID, wet=0.15)
    place(fx, sfx_splash(), at(32, 0.42), 0.7, rv=IR_MID, wet=0.25)
    place(fx, sfx_thud(32, 1.6, 1.4), at(32, 0.86), 1.0, rv=IR_BIG, wet=0.5)
    return fx.astype(np.float32)


def main():
    od = sys.argv[1]
    tl = json.load(open(os.path.join(od, "timeline.json")))
    total = tl["total"]
    tl = tl["scenes"]
    n = int(total * SR)
    sr, v = wavfile.read(os.path.join(od, "voice.wav"))
    v = v.astype(np.float32) / 32768.0
    v = np.pad(v, (0, max(0, n - len(v))))[:n]
    print("music...", flush=True)
    mus = music(total, tl)
    print("fx...", flush=True)
    fx = effects(total, tl)
    # огинаюча голосу для ducking музики
    env = np.abs(v)
    env = sosfiltfilt(butter(1, 3, "low", fs=SR, output="sos"), env)
    env = np.clip(env / (np.percentile(env, 95) + 1e-9), 0, 1)
    duck = 1 - 0.45 * env
    mus_gain = 10 ** (-20 / 20)   # музика ~ -14 дБ під голосом
    fx_gain = 10 ** (-9 / 20)
    mix = np.stack([v, v]) * 1.0 + mus * mus_gain * duck + fx * fx_gain
    peak = np.abs(mix).max()
    if peak > 0.97:
        mix *= 0.97 / peak
    wavfile.write(os.path.join(od, "mix_raw.wav"), SR, (mix.T * 32767).astype(np.int16))
    print("ok", flush=True)


if __name__ == "__main__":
    main()
