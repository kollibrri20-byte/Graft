"""Final assembly: frames -> 1080x1920 video with dips to black (shots 26-28), captions (2-3 words, white,
keyword in yellow, lower third), subscribe button on the end card, mixed audio -> final.mp4"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/root/.claude/plugins/synced/dcc9393f-9130-4ab2-a111-4ba3d42d6ba0_d7df1b23-90d5-4b6b-8e75-416b519a8c9e/kylo-3d-shorts/skills/3d-short/assets/fonts/Montserrat-Variable.ttf"
W, H = 1080, 1920
FPS = 24
DUR = 94.0
L = json.load(open(os.path.join(HERE, "lines_raw.json")))
S = [0.0] + [round(l["at"] - 0.25, 2) for l in L[1:]] + [DUR]

KEY = {"годинникар", "еліас", "назад", "сміялися", "дивну", "ім'я", "мешканців", "нулі", "зникала", "ліна", "бабусі", "зблід",
       "ім'ям", "хвилина", "побігла", "туман", "швидше", "тридцять", "дім", "вікна", "десять", "обійняла", "стиснула", "тріснуло",
       "секунді", "тиша", "цок", "вперед", "сто", "зникла", "пил", "вкрасти", "подарувати", "долоню", "підпишись"}


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def font(size, weight="ExtraBold"):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def chunks(words):
    out, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        brk = re.search(r"[.,!?;:…»—]$", w["raw"]) or (nxt is None) or (nxt["line"] != w["line"]) or len(cur) >= 3
        if len(cur) == 2 and nxt and nxt["line"] == w["line"] and len(norm(nxt["w"])) <= 2:
            brk = False
        if brk:
            out.append(cur)
            cur = []
    res = []
    for k, c in enumerate(out):
        s = c[0]["s"]
        e = out[k + 1][0]["s"] if k + 1 < len(out) else c[-1]["e"] + 0.5
        e = min(e, c[-1]["e"] + 0.45)
        res.append((c, s, max(e, s + 0.3)))
    return res


def caption_png(ws, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 84
    parts = [(w["w"].upper(), norm(w["w"]) in KEY) for w in ws]
    while True:
        f = font(size)
        stroke = max(6, size // 9)
        widths = [d.textbbox((0, 0), p, font=f, stroke_width=stroke)[2] for p, _ in parts]
        space = size * 0.32
        total = sum(widths) + space * (len(parts) - 1)
        if total < W * 0.88 or size < 44:
            break
        size -= 4
    x = (W - total) / 2
    y = H * 0.74
    for (p, key), wd in zip(parts, widths):
        d.text((x + 3, y + 7), p, font=f, fill=(0, 0, 0, 140), stroke_width=stroke, stroke_fill=(0, 0, 0, 140), anchor="lm")
        d.text((x, y), p, font=f, fill=(255, 210, 0, 255) if key else (255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255), anchor="lm")
        x += wd + space
    img.save(path)


def subscribe_png(path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(60)
    txt = "ПІДПИСАТИСЯ"
    bw = d.textbbox((0, 0), txt, font=f)[2] + 150
    bh = 120
    x0, y0 = (W - bw) / 2, H * 0.86
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=60, fill=(220, 20, 30, 255))
    # bell icon (simple)
    cx, cy = x0 + 70, y0 + bh / 2
    d.pieslice([cx - 24, cy - 30, cx + 24, cy + 20], 180, 360, fill=(255, 255, 255, 255))
    d.rectangle([cx - 24, cy - 6, cx + 24, cy + 14], fill=(255, 255, 255, 255))
    d.ellipse([cx - 7, cy + 14, cx + 7, cy + 26], fill=(255, 255, 255, 255))
    d.text((x0 + 115, y0 + bh / 2), txt, font=f, fill=(255, 255, 255, 255), anchor="lm")
    img.save(path)


def main():
    tmp = os.path.join(HERE, "post_tmp")
    os.makedirs(tmp, exist_ok=True)
    words = json.load(open(os.path.join(HERE, "words.json")))
    ch = chunks(words)
    blank = os.path.join(tmp, "blank.png")
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    lines, tcur = [], 0.0
    for k, (c, s, e) in enumerate(ch):
        if s > tcur + 0.01:
            lines += [f"file '{blank}'", f"duration {s - tcur:.3f}"]
        p = os.path.join(tmp, f"c{k:03d}.png")
        caption_png(c, p)
        lines += [f"file '{p}'", f"duration {e - s:.3f}"]
        tcur = e
    lines += [f"file '{blank}'", f"duration {max(0.1, DUR - tcur):.3f}", f"file '{blank}'"]
    open(os.path.join(tmp, "caps.txt"), "w").write("\n".join(lines))
    caps = os.path.join(tmp, "caps.mov")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "caps.txt"),
                    "-vf", f"fps={FPS},format=argb", "-c:v", "qtrle", caps], check=True)
    sub = os.path.join(tmp, "subscribe.png")
    subscribe_png(sub)
    # brightness envelope: fade in at the start, dips to black at shots 26/27/28, hard black between 35 and the end card
    dips = "*".join(f"min(1,abs(T-{c:.2f})/0.42)" for c in (S[25], S[26], S[27]))
    env = f"min(1,T/0.4)*{dips}*if(between(T,{S[35] - 0.0:.2f},{S[35] + 0.25:.2f}),0,1)"
    vf = (f"[0:v]format=yuv444p,geq=lum='lum(X,Y)*({env})':cb='128+(cb(X,Y)-128)*({env})':cr='128+(cr(X,Y)-128)*({env})',"
          f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.6,vignette=angle=0.3,format=yuv420p[v0];"
          f"[v0][1:v]overlay=format=auto[v1];"
          f"[2:v]format=rgba,fade=t=in:st={S[35] + 1.6:.2f}:d=0.5:alpha=1[sb];"
          f"[v1][sb]overlay=format=auto:enable='gte(t,{S[35] + 1.6:.2f})'[v]")
    out = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "final.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(HERE, "frames", "f%05d.png"),
                    "-i", caps, "-loop", "1", "-framerate", str(FPS), "-t", str(DUR), "-i", sub, "-i", os.path.join(HERE, "mix.wav"),
                    "-filter_complex", vf, "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-r", str(FPS), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "256k", "-t", str(DUR), "-movflags", "+faststart", out],
                   check=True)
    print("done", out, len(ch), "captions")


if __name__ == "__main__":
    main()
