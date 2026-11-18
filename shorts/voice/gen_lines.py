"""Synthesize every script line with the offline Ukrainian model, stresses taken from the acute accents."""
import os, sys, importlib.util, numpy as np, soundfile as sf, torch
from espnet2.bin.tts_inference import Text2Speech
from kaldiio import load_ark
M = "/tmp/claude-0/uatts/models"
spec = importlib.util.spec_from_file_location("fmt", os.path.join(os.path.dirname(__import__("espnet2").__file__), "..", "ukrainian_tts", "formatter.py"))
fmt = importlib.util.module_from_spec(spec); spec.loader.exec_module(fmt)
cwd = os.getcwd()
os.chdir(M)
tts = Text2Speech(train_config="config.yaml", model_file="model.pth", device="cpu")
xv = {k: v for k, v in load_ark("spk_xvector.ark")}
os.chdir(cwd)
ACC = "́"


def plus(s):
    out = []
    for ch in s:
        if ch == ACC and out:
            v = out.pop()
            out.append("+" + v)
        else:
            out.append(ch)
    return "".join(out)


def say(text, voice):
    t = plus(text.replace("...", ",").replace("…", ",").replace("—", ",").replace(":", ",")).lower()
    t = fmt.preprocess_text(t)
    with torch.no_grad():
        w = tts(t, spembs=xv[voice][0])["wav"].view(-1).numpy()
    return w


src, outdir, voice = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(outdir, exist_ok=True)
for i, line in enumerate(l.strip() for l in open(src) if l.strip()):
    if line.startswith("WHISPER:"):
        a, b = line[8:].split("|")
        sf.write(os.path.join(outdir, f"l{i:02d}_w.wav"), say(a, "dmytro"), tts.fs)
        sf.write(os.path.join(outdir, f"l{i:02d}.wav"), say(b, voice), tts.fs)
    else:
        sf.write(os.path.join(outdir, f"l{i:02d}.wav"), say(line.strip(". "), voice), tts.fs)
    print("line", i, flush=True)
