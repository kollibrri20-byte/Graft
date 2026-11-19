"""Обробка голосу, таймлайн сцен, субтитри й глибиномір (ASS).

    python build_timeline.py VOICE_DIR OUT_DIR

Голос: кожна фраза окремо проходить rubberband (темп за настроєм, тон -1 півтон зі збереженням
формант — глибший "документальний" тембр), далі склеюється з паузами, EQ/компресія/легка кімната,
нормалізація гучності.
"""
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

SR = 48000
TEMPO = {"calm": 1.12, "soft": 1.02, "tense": 1.15}
PAUSE_K = 0.85
LEAD_IN = 0.6      # тиша на початку сцени
TAIL = 0.55        # тиша в кінці сцени
TARGET = 480.0     # 8:00

# Глибиномір: (від, до) для кожної сцени; None — прихований (хук-флешбек)
DEPTH = [None, None, None, (0, 10), (10, 40), (40, 80), (80, 150), (150, 200), (200, 900), (900, 1200),
         (1200, 1600), (1600, 1800), (1800, 2300), (2300, 3000), (3000, 3800), (3800, 4500), (4500, 5000),
         (5000, 5400), (5400, 6000), (6000, 7000), (7000, 8336), (8336, 9000), (9000, 9400), (9400, 9800),
         (9800, 10200), (10200, 10600), (10600, 10800), (10800, 10900), (10900, 10935), (10935, 10935),
         (10935, 10935), (10935, 10935)]
# Хвилини (від 0 до 1 у сцені), коли глибиномір має досягти "кінцевого" значення
# Великі числа по центру: сцена -> (текст, частка часу появи)
BIG = {1: ("1960", 0.05), 5: ("11 км", 0.45), 6: ("1000 атмосфер", 0.75), 21: ("8336 м", 0.05),
       30: ("10 935 м", 0.45)}


def read_wav(path):
    sr, x = wavfile.read(path)
    x = x.astype(np.float32) / 32768.0
    return sr, x


def process_segment(path, mood, tmp):
    out = os.path.join(tmp, os.path.basename(path).replace(".wav", "_p.wav"))
    t = TEMPO[mood]
    af = (f"aresample={SR}:resampler=soxr,rubberband=tempo={t}:pitch=0.9439:formant=preserved:"
          f"pitchq=quality:transients=smooth:window=long")
    if os.environ.get("NATURAL"):
        # природний голос (HolosTTS): без зміни темпу й тону
        af = f"aresample={SR}:resampler=soxr"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-af", af, "-ac", "1", out], check=True)
    return read_wav(out)[1]


def syllables(s):
    return max(1, sum(c in "аеєиіїоуюяАЕЄИІЇОУЮЯ" for c in s))


def chunk_words(text, maxw=5):
    """Розбити речення на субтитри по 3-5 слів, бажано на межі розділових знаків."""
    words = text.split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= maxw or (len(cur) >= 3 and re.search(r"[,:;—.!?…]$", w)):
            out.append(cur)
            cur = []
    if cur:
        if len(cur) < 2 and out:
            out[-1] += cur
        else:
            out.append(cur)
    return [" ".join(c) for c in out]


def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def fmt_depth(v):
    return f"{int(round(v)):,}".replace(",", " ")


def main():
    vdir, odir = sys.argv[1], sys.argv[2]
    tmp = os.path.join(odir, "vtmp")
    os.makedirs(tmp, exist_ok=True)
    man = json.load(open(os.path.join(vdir, "manifest.json")))
    scenes = []
    for sc in man["scenes"]:
        segs = []
        for sg in sc["segments"]:
            wav = process_segment(sg["file"], sg["mood"], tmp)
            segs.append(dict(sg, wav=wav, pdur=len(wav) / SR, pause=sg["pause"] * PAUSE_K))
        speech = sum(s["pdur"] + s["pause"] for s in segs) - segs[-1]["pause"]
        scenes.append(dict(scene=sc["scene"], segs=segs, speech=speech))
        print(f"scene {sc['scene']:2d}: {speech:5.1f}s", flush=True)

    # тривалості сцен: голос + поля, решту до 8:00 розподіляємо пропорційно
    base = [s["speech"] + LEAD_IN + TAIL for s in scenes]
    extra = max(TARGET - sum(base), 0)
    weights = np.array([max(b, 6) for b in base])
    add = extra * weights / weights.sum()
    # фінальна сцена має довгий хвіст для "очей" у темряві
    durs = [b + a for b, a in zip(base, add)]
    durs[-1] += 4.0
    if os.environ.get("FIXED_TL"):
        # зберегти тривалості сцен попередньої версії (щоб не перерендерювати 3D-сцени без ведучого)
        durs = [x["dur"] for x in json.load(open(os.environ["FIXED_TL"]))["scenes"]]
        for sc_, d in zip(scenes, durs):
            room = d - LEAD_IN - TAIL
            if sc_["speech"] > room:
                pauses = sum(g["pause"] for g in sc_["segs"][:-1])
                k = max(0.35, 1 - (sc_["speech"] - room) / max(pauses, 1e-6))
                for g in sc_["segs"]:
                    g["pause"] *= k
                sc_["speech"] = sum(g["pdur"] + g["pause"] for g in sc_["segs"]) - sc_["segs"][-1]["pause"]
                print(f"scene {sc_['scene']}: pauses x{k:.2f} -> {sc_['speech']:.1f}s / room {room:.1f}s")
    t0 = 0.0
    voice = np.zeros(int((sum(durs) + 1) * SR), np.float32)
    subs, timeline, seglog = [], [], []
    for s, d in zip(scenes, durs):
        lead = LEAD_IN + max(0.0, d - s["speech"] - LEAD_IN - TAIL) * 0.35
        if s["scene"] == 32:
            lead = LEAD_IN + 2.0
        t = t0 + lead
        for si_, sg in enumerate(s["segs"]):
            seglog.append(dict(scene=s["scene"], idx=si_, start=t, end=t + sg["pdur"], text=sg["text"], mood=sg["mood"]))
            i = int(t * SR)
            voice[i:i + len(sg["wav"])] += sg["wav"]
            # субтитри: розподіл часу пропорційно складам
            chunks = chunk_words(sg["text"])
            tot = sum(syllables(c) for c in chunks)
            ct = t
            for c in chunks:
                cd = sg["pdur"] * syllables(c) / tot
                subs.append((ct, ct + cd, c))
                ct += cd
            t += sg["pdur"] + sg["pause"]
        timeline.append(dict(scene=s["scene"], start=t0, dur=d, voice_start=t0 + lead))
        t0 += d
    total = t0
    voice = voice[: int(total * SR)]
    raw = os.path.join(tmp, "voice_raw.wav")
    wavfile.write(raw, SR, (np.clip(voice, -1, 1) * 32767).astype(np.int16))
    # Обробка голосу: прибрати гул, теплий низ, трохи присутності, м'яка компресія, ледь помітна кімната
    af = ("highpass=f=70,lowpass=f=11000,"
          "equalizer=f=140:t=q:w=1.0:g=3,equalizer=f=320:t=q:w=1.2:g=-2,"
          "equalizer=f=3200:t=q:w=1.4:g=2,equalizer=f=7000:t=q:w=2:g=-2,"
          "acompressor=threshold=-20dB:ratio=3:attack=8:release=180:makeup=2,"
          "aecho=0.8:0.25:38|71:0.12|0.07,"
          "loudnorm=I=-17:TP=-2:LRA=9")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", af, "-ar", str(SR), "-ac", "1",
                    os.path.join(odir, "voice.wav")], check=True)

    # ---------------- ASS: субтитри, глибиномір, великі числа
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 2",
           "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Inter SemiBold,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0.5,0,1,3.2,1.2,2,80,80,70,1",
           "Style: Depth,JetBrains Mono,50,&H00F5E6C8,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,2.5,0,9,60,70,50,1",
           "Style: DepthL,Inter Medium,24,&H00C8B89A,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,4,0,1,2,0,9,60,72,32,1",
           "Style: Big,Inter Display ExtraBold,150,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,2,0,1,4,2,5,60,60,60,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for a, b, txt in subs:
        ass.append(f"Dialogue: 2,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{txt}")
    step = 1 / 12
    for tl, dp in zip(timeline, DEPTH):
        if dp is None:
            continue
        a, b = dp
        n = int(tl["dur"] / step)
        ass.append(f"Dialogue: 1,{ass_time(tl['start'])},{ass_time(tl['start'] + tl['dur'])},DepthL,,0,0,0,,ГЛИБИНА")
        for k in range(n):
            u = k / max(n - 1, 1)
            if tl["scene"] == 21:  # 8336 м має з'явитися одразу, коли звучить число
                u = min(u / 0.08, 1)
            v = a + (b - a) * (u * u * (3 - 2 * u))
            st = tl["start"] + k * step
            ass.append(f"Dialogue: 1,{ass_time(st)},{ass_time(st + step + 0.01)},Depth,,0,0,0,,{fmt_depth(v)} м")
    for tl in timeline:
        if tl["scene"] in BIG:
            txt, u = BIG[tl["scene"]]
            st = tl["voice_start"] + (tl["dur"] - (tl["voice_start"] - tl["start"])) * u
            ass.append(f"Dialogue: 3,{ass_time(st)},{ass_time(st + 1.8)},Big,,0,0,0,,{{\\fad(250,350)}}{txt}")
    with open(os.path.join(odir, "overlay.ass"), "w") as f:
        f.write("\n".join(ass) + "\n")
    json.dump(dict(total=total, scenes=timeline), open(os.path.join(odir, "timeline.json"), "w"), indent=1)
    json.dump(seglog, open(os.path.join(odir, "segments.json"), "w"), indent=1, ensure_ascii=False)
    print(f"total {total:.1f}s ({int(total // 60)}:{total % 60:04.1f})")


if __name__ == "__main__":
    main()
