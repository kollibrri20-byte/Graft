"""Синтез озвучки локальною моделлю ukrainian-tts (ESPnet VITS, v6.0.0).

Запуск (у venv з espnet==202301, torch 2.0):
    python tts.py MODEL_DIR OUT_DIR [voice] [--test]

Наголоси беруться ТІЛЬКИ з voice_script.py ('+' перед голосною), без автоматичного
словника. Кожна фраза синтезується окремо, далі склеюється з паузами заданої довжини;
на "soft"-фразах темп повільніший, а гучність нижча.
"""
import json
import os
import re
import sys

import numpy as np
import soundfile as sf
import torch
from espnet2.bin.tts_inference import Text2Speech
from kaldiio import load_ark

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_script import SCENES  # noqa: E402

VOWELS = "аеєиіїоуюя"
# Tacotron2 + HiFi-GAN, 22.05 кГц; темп змінюється пізніше в post.py (rubberband)

# speed: коефіцієнт тривалості (>1 — повільніше), застосовується в post.py; gain у дБ
MOODS = {
    "calm": dict(speed=1.10, gain=0.0, noise=0.55),
    "soft": dict(speed=1.22, gain=-3.0, noise=0.50),
    "tense": dict(speed=1.04, gain=0.5, noise=0.60),
}
PAUSE_SENT = 0.50   # між реченнями
PAUSE_ELLIPSIS = 0.80
PAUSE_QUESTION = 0.65


def stress_monosyllables(text):
    """Модель навчена на тексті, де наголос є в кожному слові, і в односкладових теж."""
    def fix(m):
        w = m.group(0)
        if "+" in w:
            return w
        idx = [i for i, c in enumerate(w) if c in VOWELS]
        if len(idx) == 1:
            return w[: idx[0]] + "+" + w[idx[0]:]
        return w
    return re.sub(r"[а-яіїєґ'+]+", fix, text)


def normalize(text):
    text = text.lower().replace("’", "'").replace("ʼ", "'")
    text = text.replace(" — ", ", ").replace("—", ",")
    text = text.replace(":", ",")
    text = re.sub(r"\s+", " ", text).strip()
    return stress_monosyllables(text)


def split_phrase(text):
    """Розбити фразу на частини по '…' (довга пауза)."""
    parts = [p.strip() for p in text.split("…")]
    return [p for p in parts if p]


def main():
    model_dir, out_dir = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else "mykyta"
    test = "--test" in sys.argv
    os.makedirs(out_dir, exist_ok=True)
    torch.set_num_threads(4)
    tts = Text2Speech(
        train_config=os.path.join(model_dir, "config.yaml"),
        model_file=os.path.join(model_dir, "model.pth"),
        device="cpu",
    )
    xv = {k: v for k, v in load_ark(os.path.join(model_dir, "spk_xvector.ark"))}
    spk = xv[voice][0] if np.ndim(xv[voice]) > 1 else xv[voice]
    spk = torch.tensor(np.asarray(spk), dtype=torch.float32)
    fs = tts.fs

    def synth_once(text):
        with torch.no_grad():
            wav = tts(text, spembs=spk)["wav"].view(-1).cpu().numpy()
        thr = 0.02 * np.abs(wav).max()
        nz = np.where(np.abs(wav) > thr)[0]
        wav = wav[max(nz[0] - int(0.03 * fs), 0): nz[-1] + int(0.08 * fs)].copy()
        fade = int(0.01 * fs)
        wav[:fade] *= np.linspace(0, 1, fade)
        wav[-fade:] *= np.linspace(1, 0, fade)
        return wav

    def synth(text):
        """Tacotron2 інколи "зриває" увагу (ковтає кінець або белькоче).
        Робимо кілька дублів і беремо той, чий темп найближчий до норми."""
        n = sum(c in VOWELS for c in text)  # кількість складів
        takes = []
        for _ in range(3):
            w = synth_once(text)
            rate = n / (len(w) / fs)  # складів за секунду
            takes.append((abs(rate - 4.7), rate, w))
            if 4.0 < rate < 5.6:
                break
        takes.sort(key=lambda x: x[0])
        return takes[0][2], takes[0][1]

    only = None
    for a in sys.argv:
        if a.startswith("--only="):
            only = {int(x) for x in a[7:].split(",")}
    scenes = SCENES[:3] if test else SCENES
    man_path = os.path.join(out_dir, "manifest.json")
    manifest = {}
    if os.path.exists(man_path):
        manifest = {s["scene"]: s for s in json.load(open(man_path))["scenes"]}
    for si, (mood0, phrases) in enumerate(scenes, 1):
        if only and si not in only:
            continue
        mood = mood0
        segs = []
        for ph in phrases:
            m = re.match(r"@(\w+)\s+(.*)", ph)
            if m:
                mood, ph = m.group(1), m.group(2)
            pieces = split_phrase(ph)
            for k, piece in enumerate(pieces):
                text = normalize(piece)
                wav, rate = synth(text)
                last = k == len(pieces) - 1
                if not last:
                    pause = PAUSE_ELLIPSIS
                elif ph.rstrip().endswith("?"):
                    pause = PAUSE_QUESTION
                else:
                    pause = PAUSE_SENT + (0.15 if mood == "soft" else 0)
                path = os.path.join(out_dir, f"s{si:02d}_{len(segs):02d}.wav")
                sf.write(path, wav, fs, "PCM_16")
                display = piece.replace("+", "") + ("…" if not last else "")
                segs.append(dict(file=path, mood=mood, pause=pause, text=display,
                                 tts_text=text, dur=len(wav) / fs, rate=rate))
                print(f"[{si:02d}] {mood:5s} {rate:4.1f} syl/s {len(wav)/fs:5.2f}s  {text}", flush=True)
        manifest[si] = dict(scene=si, segments=segs)
        with open(man_path, "w") as f:
            json.dump(dict(fs=fs, voice=voice, scenes=[manifest[k] for k in sorted(manifest)]),
                      f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
