"""Animated end overlay: cursor clicks LIKE, SUBSCRIBE, BELL -> PNG sequence (RGBA 1080x1920, 24 fps)."""
import math
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "/root/.claude/plugins/synced/dcc9393f-9130-4ab2-a111-4ba3d42d6ba0_d7df1b23-90d5-4b6b-8e75-416b519a8c9e/kylo-3d-shorts/skills/3d-short/assets/fonts/Montserrat-Variable.ttf"
W, H, FPS = 1080, 1920, 24
SS = 2  # supersampling


def font(size):
    f = ImageFont.truetype(FONT, size * SS)
    try:
        f.set_variation_by_name("ExtraBold")
    except Exception:
        pass
    return f


def clamp(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def pop(x):
    """0 -> overshoot -> 1"""
    x = clamp(x)
    return 1 + 0.25 * math.sin(math.pi * x) * (1 - x) * 3 - (1 - x) ** 3 if x > 0 else 0.0


def thumb(d, cx, cy, s, fill, outline):
    # cuff + fist + thumb, centred at cx, cy, size s
    w = s
    d.rounded_rectangle([cx - 0.52 * w, cy - 0.05 * w, cx - 0.30 * w, cy + 0.45 * w], radius=0.05 * w, fill=fill, outline=outline, width=int(0.06 * w))
    d.rounded_rectangle([cx - 0.24 * w, cy - 0.10 * w, cx + 0.48 * w, cy + 0.45 * w], radius=0.12 * w, fill=fill, outline=outline, width=int(0.06 * w))
    d.polygon([(cx - 0.20 * w, cy - 0.08 * w), (cx - 0.02 * w, cy - 0.55 * w), (cx + 0.12 * w, cy - 0.52 * w), (cx + 0.10 * w, cy - 0.10 * w)],
              fill=fill, outline=outline)
    d.ellipse([cx - 0.07 * w, cy - 0.62 * w, cx + 0.15 * w, cy - 0.42 * w], fill=fill, outline=outline, width=int(0.06 * w))
    for k in range(3):
        y = cy + (0.03 + k * 0.14) * w
        d.line([(cx + 0.05 * w, y), (cx + 0.46 * w, y)], fill=outline, width=int(0.05 * w))


def bell(d, cx, cy, s, ang, fill, outline):
    # draw on a temporary layer and rotate around the top
    lay = Image.new("RGBA", (int(2 * s), int(2 * s)), (0, 0, 0, 0))
    q = ImageDraw.Draw(lay)
    c = s
    q.pieslice([c - 0.5 * s, c - 0.62 * s, c + 0.5 * s, c + 0.38 * s], 180, 360, fill=fill, outline=outline, width=int(0.06 * s))
    q.rectangle([c - 0.5 * s, c - 0.13 * s, c + 0.5 * s, c + 0.32 * s], fill=fill)
    q.line([(c - 0.5 * s, c - 0.13 * s), (c - 0.5 * s, c + 0.32 * s)], fill=outline, width=int(0.06 * s))
    q.line([(c + 0.5 * s, c - 0.13 * s), (c + 0.5 * s, c + 0.32 * s)], fill=outline, width=int(0.06 * s))
    q.rounded_rectangle([c - 0.66 * s, c + 0.28 * s, c + 0.66 * s, c + 0.42 * s], radius=0.06 * s, fill=fill, outline=outline, width=int(0.05 * s))
    q.ellipse([c - 0.13 * s, c + 0.44 * s, c + 0.13 * s, c + 0.66 * s], fill=outline)
    q.ellipse([c - 0.08 * s, c - 0.78 * s, c + 0.08 * s, c - 0.6 * s], fill=outline)
    lay = lay.rotate(ang, center=(c, c - 0.7 * s), resample=Image.BICUBIC)
    return lay, (int(cx - c), int(cy - c))


def cursor(d, x, y, s, press):
    k = 0.85 if press else 1.0
    s = s * k
    pts = [(0, 0), (0, 1.0), (0.26, 0.78), (0.45, 1.18), (0.6, 1.1), (0.42, 0.72), (0.75, 0.72)]
    P = [(x + px * s, y + py * s) for px, py in pts]
    d.polygon([(px + 6, py + 8) for px, py in P], fill=(0, 0, 0, 110))
    d.polygon(P, fill=(255, 255, 255, 255), outline=(20, 20, 20, 255))
    d.line(P + [P[0]], fill=(20, 20, 20, 255), width=int(0.06 * s))


def frame(tau):
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = H * 0.875 * SS
    # layout
    like_c = (W * 0.17 * SS, cy)
    bell_c = (W * 0.83 * SS, cy)
    sub_c = (W * 0.5 * SS, cy)
    R = 78 * SS
    # click times
    t_like, t_sub, t_bell = 1.35, 2.25, 3.1
    # LIKE
    a = pop((tau - 0.0) / 0.45)
    if a > 0:
        liked = tau >= t_like
        r = R * a * (1 + 0.15 * math.exp(-max(0, tau - t_like) * 8) * (tau >= t_like))
        d.ellipse([like_c[0] - r, like_c[1] - r, like_c[0] + r, like_c[1] + r], fill=(255, 255, 255, 235) if liked else (25, 25, 30, 200),
                  outline=(255, 255, 255, 255), width=4 * SS)
        thumb(d, like_c[0] + 4 * SS, like_c[1] + 6 * SS, r * 0.95, (40, 120, 255, 255) if liked else (255, 255, 255, 255),
              (20, 60, 160, 255) if liked else (255, 255, 255, 255))
        if liked and tau < t_like + 0.6:  # burst
            u = (tau - t_like) / 0.6
            for k in range(10):
                ang = 2 * math.pi * k / 10
                r0, r1 = R * (1.1 + 0.6 * u), R * (1.3 + 0.9 * u)
                d.line([(like_c[0] + r0 * math.cos(ang), like_c[1] + r0 * math.sin(ang)),
                        (like_c[0] + r1 * math.cos(ang), like_c[1] + r1 * math.sin(ang))], fill=(255, 210, 0, int(255 * (1 - u))), width=7 * SS)
    # SUBSCRIBE
    a = pop((tau - 0.12) / 0.45)
    if a > 0:
        subbed = tau >= t_sub
        txt = "ПІДПИСАНО" if subbed else "ПІДПИСАТИСЯ"
        f = font(int(46 * a)) if a > 0.05 else font(1)
        tw = d.textbbox((0, 0), txt, font=f)[2]
        bw, bh = tw + 90 * SS * a, 120 * SS * a
        bump = 1 + 0.12 * math.exp(-max(0, tau - t_sub) * 8) * (tau >= t_sub)
        bw, bh = bw * bump, bh * bump
        x0, y0 = sub_c[0] - bw / 2, sub_c[1] - bh / 2
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh / 2, fill=(90, 90, 95, 240) if subbed else (225, 20, 30, 255))
        d.text(sub_c, txt, font=f, fill=(255, 255, 255, 255), anchor="mm")
    # BELL
    a = pop((tau - 0.24) / 0.45)
    if a > 0:
        rung = tau >= t_bell
        r = R * a
        d.ellipse([bell_c[0] - r, bell_c[1] - r, bell_c[0] + r, bell_c[1] + r], fill=(255, 255, 255, 235) if rung else (25, 25, 30, 200),
                  outline=(255, 255, 255, 255), width=4 * SS)
        dt = tau - t_bell
        ang = 24 * math.sin(dt * 28) * math.exp(-dt * 2.2) if rung else 0
        lay, off = bell(d, bell_c[0], bell_c[1] + 4 * SS, r * 0.9, ang, (255, 200, 0, 255) if rung else (255, 255, 255, 255),
                        (150, 100, 0, 255) if rung else (255, 255, 255, 255))
        img.alpha_composite(lay, off)
        if rung and dt < 1.2:
            for side in (-1, 1):
                for k in range(2):
                    rr = r * (1.15 + 0.22 * k)
                    al = int(255 * max(0, 1 - dt / 1.2) * (0.5 + 0.5 * math.sin(dt * 20 + k)))
                    box = [bell_c[0] - rr, bell_c[1] - rr, bell_c[0] + rr, bell_c[1] + rr]
                    d.arc(box, 200 if side < 0 else -20, 250 if side < 0 else 30, fill=(255, 210, 0, al), width=6 * SS)
    # CURSOR path
    if 0.7 <= tau <= 4.6:
        pts = [(0.7, (W * 0.95 * SS, H * 1.02 * SS)), (t_like - 0.05, (like_c[0], like_c[1])), (t_like + 0.35, (like_c[0], like_c[1])),
               (t_sub - 0.05, (sub_c[0] + 40 * SS, sub_c[1])), (t_sub + 0.3, (sub_c[0] + 40 * SS, sub_c[1])),
               (t_bell - 0.05, (bell_c[0], bell_c[1])), (t_bell + 0.6, (bell_c[0], bell_c[1])), (4.6, (W * 1.05 * SS, H * 1.05 * SS))]
        for (ta, pa), (tb, pb) in zip(pts, pts[1:]):
            if ta <= tau <= tb:
                u = ease((tau - ta) / (tb - ta))
                x, y = pa[0] + (pb[0] - pa[0]) * u, pa[1] + (pb[1] - pa[1]) * u
                break
        press = any(abs(tau - tc) < 0.08 for tc in (t_like, t_sub, t_bell))
        cursor(d, x + 10 * SS, y + 10 * SS, 70 * SS, press)
    return img.resize((W, H), Image.LANCZOS)


def build(out_dir, dur=4.8):
    os.makedirs(out_dir, exist_ok=True)
    n = int(dur * FPS)
    for k in range(n):
        frame(k / FPS).save(os.path.join(out_dir, f"e{k + 1:04d}.png"))
    return n


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        frame(float(sys.argv[1])).save("/tmp/claude-0/endcard.png")
    else:
        print(build(os.path.join(os.path.dirname(os.path.abspath(__file__)), "post_tmp", "end")))
