"""Озвучка HolosTTS (голос Speaker_36) з ручними наголосами з voice_script.py.

    HF_HUB_DISABLE_XET=1 python tts_holos.py OUT_DIR [VOICE]
Формат виходу такий самий, як у tts.py (manifest.json + s{сцена}_{фраза}.wav), тож build_timeline.py працює без змін.
Наголос: '+' перед голосною в voice_script.py -> комбінований акут після голосної (формат HolosTTS).
Скрипт перевіряє, що після stressify() наголос у кожному слові збігся з ручним.
"""
import json
import os
import re
import sys
from unicodedata import normalize

import numpy as np
import soundfile as sf
from holos.models import HolosTTS
from ipa_uk import ipa
from ukrainian_word_stress import Stressifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_script import SCENES  # noqa: E402

V = "аеєиіїоуюяАЕЄИІЇОУЮЯ"
ACUTE = "́"
SPEED = {"calm": 0.94, "soft": 0.86, "tense": 1.0}
GAIN = {"calm": 0.0, "soft": -3.0, "tense": 0.5}
PAUSE_SENT, PAUSE_ELLIPSIS, PAUSE_Q = 0.5, 0.8, 0.65


def conv(s):
    return re.sub(r"\+([%s])" % V, lambda m: m.group(1) + ACUTE, s)


def stress_positions(s):
    """слово -> індекс наголошеної голосної (рахуючи лише літери)."""
    out = []
    for w in re.findall(r"[\w'ʼ%s-]+" % ACUTE, s):
        letters = w.replace(ACUTE, "")
        pos = [i for i, c in enumerate(w) if c == ACUTE]
        idx = [p - 1 - k for k, p in enumerate(pos)]
        out.append((letters.lower(), idx))
    return out


def main():
    out_dir = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else "Speaker_36"
    os.makedirs(out_dir, exist_ok=True)
    stressify = Stressifier()
    m = HolosTTS("patriotyk/HolosTTS", device="cpu")
    fs = 24000
    manifest, problems = [], []
    for si, (mood0, phrases) in enumerate(SCENES, 1):
        mood = mood0
        segs = []
        for ph in phrases:
            mm = re.match(r"@(\w+)\s+(.*)", ph)
            if mm:
                mood, ph = mm.group(1), mm.group(2)
            pieces = [p.strip() for p in ph.split("…") if p.strip()]
            for k, piece in enumerate(pieces):
                manual = normalize("NFC", conv(piece))
                t = re.sub(r"\s+—\s+", ", ", manual)
                if t[-1] not in ".?!:":
                    t += "."
                t2 = stressify(t)
                # перевірка: модель не змінила ручних наголосів
                a = [x for x in stress_positions(t) if x[1]]
                b = dict()
                for w, idx in stress_positions(t2):
                    b.setdefault(w, idx)
                for w, idx in a:
                    if w in b and b[w][:1] != idx[:1]:
                        problems.append((si, w, idx, b[w]))
                ps = ipa(t2)
                w = m.generate(ps, voice, speed=SPEED[mood]).squeeze().cpu().numpy().astype(np.float32)
                thr = 0.02 * np.abs(w).max()
                nz = np.where(np.abs(w) > thr)[0]
                w = w[max(nz[0] - int(0.03 * fs), 0): nz[-1] + int(0.08 * fs)]
                w = w * 10 ** (GAIN[mood] / 20)
                last = k == len(pieces) - 1
                pause = PAUSE_ELLIPSIS if not last else (PAUSE_Q if ph.rstrip().endswith("?") else PAUSE_SENT + (0.15 if mood == "soft" else 0))
                path = os.path.join(out_dir, f"s{si:02d}_{len(segs):02d}.wav")
                sf.write(path, w, fs, "PCM_16")
                segs.append(dict(file=path, mood=mood, pause=pause, text=piece.replace("+", "") + ("…" if not last else ""),
                                 tts_text=t2, dur=len(w) / fs))
                print(f"[{si:02d}] {mood:5s} {len(w)/fs:5.2f}s {t2}", flush=True)
        manifest.append(dict(scene=si, segments=segs))
    json.dump(dict(fs=fs, voice=voice, scenes=manifest), open(os.path.join(out_dir, "manifest.json"), "w"),
              indent=1, ensure_ascii=False)
    print("STRESS CHANGED BY MODEL:", len(problems))
    for p in problems:
        print("  ", p)


if __name__ == "__main__":
    main()
