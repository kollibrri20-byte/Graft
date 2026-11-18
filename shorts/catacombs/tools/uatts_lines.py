"""Neural Ukrainian narration (robinhad/ukrainian-tts v6, Tacotron2 + HiFiGAN via espnet), one wav per line.
Text is pre-stressed by hand ('+' before the stressed vowel, every word), so no stanza/accentor is needed.
  python uatts_lines.py <model_dir> <stressed_lines.txt> <out_dir> <voice> [seed]"""
import os, sys, random
import numpy as np, soundfile as sf, torch
from espnet2.bin.tts_inference import Text2Speech
from kaldiio import load_ark
mdir, lines_path, out, voice = sys.argv[1:5]
seed = int(sys.argv[5]) if len(sys.argv) > 5 else 1
os.chdir(mdir)
tts = Text2Speech(train_config="config.yaml", model_file="model.pth", device="cpu")
xv = {k: v for k, v in load_ark("spk_xvector.ark")}
os.makedirs(out, exist_ok=True)
for i, line in enumerate(l.strip() for l in open(lines_path, encoding="utf-8") if l.strip()):
    torch.manual_seed(seed + i); random.seed(seed + i); np.random.seed(seed + i)
    with torch.no_grad():
        wav = tts(line.lower(), spembs=xv[voice][0])["wav"]
    sf.write(os.path.join(out, f"{voice}_{i}.wav"), wav.view(-1).cpu().numpy(), tts.fs, "PCM_16")
    print(voice, i, f"{len(wav) / tts.fs:.2f}s", line)
