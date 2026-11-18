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
SR = 48000  # модель видає 48 кГц

# темп (length scale: >1 — повільніше), гучність (дБ)
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
    return re.sub(r"[а-яіїєґ']+", fix, text)


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

    def synth(text, mood):
        p = MOODS[mood]
        tts.decode_conf.update(
            dict(alpha=p["speed"], noise_scale=p["noise"], noise_scale_dur=0.8)
        )
        with torch.no_grad():
            wav = tts(text, spembs=spk)["wav"].view(-1).cpu().numpy()
        # прибрати тишу на краях
        thr = 0.01 * np.abs(wav).max()
        nz = np.where(np.abs(wav) > thr)[0]
        wav = wav[max(nz[0] - int(0.02 * fs), 0): nz[-1] + int(0.06 * fs)]
        fade = int(0.01 * fs)
        wav[:fade] *= np.linspace(0, 1, fade)
        wav[-fade:] *= np.linspace(1, 0, fade)
        return wav * 10 ** (p["gain"] / 20)

    def sil(sec):
        return np.zeros(int(sec * fs), dtype=np.float32)

    scenes = SCENES[:3] if test else SCENES
    manifest = []
    for si, (mood0, phrases) in enumerate(scenes, 1):
        mood = mood0
        chunks, words = [], []
        for ph in phrases:
            m = re.match(r"@(\w+)\s+(.*)", ph)
            if m:
                mood, ph = m.group(1), m.group(2)
            pieces = split_phrase(ph)
            for k, piece in enumerate(pieces):
                text = normalize(piece)
                print(f"[{si:02d}] {mood:5s} {text}", flush=True)
                chunks.append(synth(text, mood))
                last = k == len(pieces) - 1
                if not last:
                    chunks.append(sil(PAUSE_ELLIPSIS))
                elif ph.rstrip().endswith("?"):
                    chunks.append(sil(PAUSE_QUESTION))
                else:
                    chunks.append(sil(PAUSE_SENT + (0.15 if mood == "soft" else 0)))
        wav = np.concatenate(chunks[:-1]).astype(np.float32)
        path = os.path.join(out_dir, f"scene_{si:02d}.wav")
        sf.write(path, wav, fs, "PCM_16")
        manifest.append(dict(scene=si, file=path, dur=len(wav) / fs))
        print(f"scene {si}: {len(wav) / fs:.2f}s", flush=True)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(dict(fs=fs, voice=voice, scenes=manifest), f, indent=1)


if __name__ == "__main__":
    main()
