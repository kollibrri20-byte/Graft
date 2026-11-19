"""Розрізає посценні озвучки ElevenLabs на фрази (як у voice_script.py), щоб build_timeline.py
міг розставити їх у ті самі сцени, а ведучий і монтажні склейки потрапили на межі речень.

    python el_split.py EL_DIR OUT_DIR
EL_DIR: sc/sNN.mp3 + asr.json (Whisper, слова з таймінгами).
Межа фрази: частка літер тексту -> час за словами Whisper -> найтихіше місце поруч (±0.5 с).
Паузи між фразами вже є в аудіо, тож pause=0.
"""
import json
import os
import re
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_script import SCENES  # noqa: E402

SR = 48000


def letters(s):
    return len(re.findall(r"[а-яіїєґa-z]", s.lower()))


def num_words_uk(tok):
    """Цифри Whisper -> приблизна кількість літер у словесній формі (≈7 літер на цифру)."""
    d = re.sub(r"\D", "", tok)
    return 7 * len(d) if d else 0


def main():
    el, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    asr = {int(k): v for k, v in json.load(open(os.path.join(el, "asr.json"))).items()}
    manifest = []
    for si, (mood0, phrases) in enumerate(SCENES, 1):
        wav_path = os.path.join(out, f"full_{si:02d}.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(el, "sc", f"s{si:02d}.mp3"),
                        "-ar", str(SR), "-ac", "1", wav_path], check=True)
        sr, x = wavfile.read(wav_path)
        x = x.astype(np.float32) / 32768
        # фрази так само, як у tts.py (розбиття по «…»)
        pieces, mood = [], mood0
        for ph in phrases:
            m = re.match(r"@(\w+)\s+(.*)", ph)
            if m:
                mood, ph = m.group(1), m.group(2)
            parts = [p.strip() for p in ph.split("…") if p.strip()]
            for k, p in enumerate(parts):
                pieces.append((p.replace("+", "") + ("…" if k < len(parts) - 1 else ""), mood))
        tot = sum(letters(p) for p, _ in pieces)
        # кумулятивні літери за словами Whisper
        words = asr[si]
        cum, acc = [], 0
        for w in words:
            acc += letters(w["w"]) + num_words_uk(w["w"])
            cum.append((acc, w["s"], w["e"]))
        wtot = max(acc, 1)
        # енергія для пошуку пауз
        hop = int(0.01 * SR)
        env = np.sqrt(np.convolve(x ** 2, np.ones(hop * 4) / (hop * 4), mode="same"))[::hop]
        bounds = [0.0]
        acc_p = 0
        for p, _ in pieces[:-1]:
            acc_p += letters(p)
            target = acc_p / tot * wtot
            t = None
            for i, (c, s, e) in enumerate(cum):
                if c >= target:
                    nxt = cum[i + 1][1] if i + 1 < len(cum) else e
                    t = (e + nxt) / 2
                    break
            if t is None:
                t = cum[-1][2]
            lo, hi = int(max(t - 0.5, bounds[-1] + 0.2) * 100), int(min(t + 0.5, len(x) / SR - 0.2) * 100)
            if hi > lo:
                t = (lo + int(np.argmin(env[lo:hi]))) / 100
            bounds.append(t)
        bounds.append(len(x) / SR)
        segs = []
        for i, (p, md) in enumerate(pieces):
            a, b = int(bounds[i] * SR), int(bounds[i + 1] * SR)
            seg = x[a:b]
            f = os.path.join(out, f"s{si:02d}_{i:02d}.wav")
            wavfile.write(f, SR, (seg * 32767).astype(np.int16))
            segs.append(dict(file=f, mood=md, pause=0.0, text=p, dur=len(seg) / SR))
        manifest.append(dict(scene=si, segments=segs))
        print(si, [round(b, 2) for b in bounds])
    json.dump(dict(fs=SR, voice="elevenlabs:Storyteller", scenes=manifest),
              open(os.path.join(out, "manifest.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
