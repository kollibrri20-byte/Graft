import sys, os, importlib.util, numpy as np, soundfile as sf, requests
from espnet2.bin.tts_inference import Text2Speech
from kaldiio import load_ark
import torch
M = "/tmp/claude-0/uatts/models"
base = "https://github.com/robinhad/ukrainian-tts/releases/download/v6.0.0/"
for f in ("model.pth", "config.yaml", "spk_xvector.ark", "feats_stats.npz"):
    p = os.path.join(M, f)
    if not os.path.exists(p):
        r = requests.get(base + f, allow_redirects=True, timeout=600); open(p, "wb").write(r.content)
spec = importlib.util.spec_from_file_location("fmt", os.path.join(os.path.dirname(__import__("espnet2").__file__), "..", "ukrainian_tts", "formatter.py"))
fmt = importlib.util.module_from_spec(spec); spec.loader.exec_module(fmt)
os.chdir(M)
tts = Text2Speech(train_config="config.yaml", model_file="model.pth", device="cpu")
xv = {k: v for k, v in load_ark("spk_xvector.ark")}
voice, out = sys.argv[1], os.path.join("/tmp/claude-0/uatts", sys.argv[2])
text = open(os.path.join("/tmp/claude-0/uatts", sys.argv[3]) if not os.path.isabs(sys.argv[3]) else sys.argv[3]).read().strip()
wavs = []
for line in text.splitlines():
    line = fmt.preprocess_text(line.strip()).lower()
    with torch.no_grad():
        w = tts(line, spembs=xv[voice][0])["wav"].view(-1).numpy()
    wavs.append(w); wavs.append(np.zeros(int(tts.fs * 0.5)))
sf.write(out, np.concatenate(wavs), tts.fs)
print("ok", out, tts.fs)
