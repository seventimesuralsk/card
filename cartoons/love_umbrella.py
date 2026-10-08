"""Мультик «Один зонт на двоих» — 1080x1920, 30 c, 30 fps, со звуком.

Всё рисуется кодом (pycairo), звук синтезируется (numpy), сборка — ffmpeg.
Запуск:  pip install pycairo numpy && python3 love_umbrella.py
"""
import math, os, random, subprocess, sys, wave
import numpy as np
import cairo

W, H, FPS, DUR = 1080, 1920, 30, 30.0
SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "love_umbrella.mp4")
TMP = os.environ.get("TMPDIR", "/tmp")
GROUND = 1500

# ---------- таймлайн (общий для картинки и звука) ----------
WALK0, WALK1, STEP = 3.5, 8.0, 0.28
STEPS = [WALK0 + k * STEP for k in range(int((WALK1 - WALK0) / STEP) + 1)]
BEATS = [8.6 + k * 0.75 for k in range(10)]
SHARE0, SHARE1 = 11.5, 13.0          # зонт переезжает на двоих
CLEAR0, CLEAR1 = 15.5, 18.0          # дождь кончается, небо светлеет
CLOSE0, CLOSE1 = 17.0, 18.5          # зонт закрывается
HANDS = 19.0                          # берутся за руки
HEART0, POP = 19.8, 23.0
END0 = 25.0

CAPTIONS = [
    (0.3, 3.4, ["Он мок под дождём", "каждый вечер…"]),
    (3.6, 8.2, ["…пока не появилась", "ОНА"]),
    (8.4, 11.6, ["Она ничего не спросила.", "Просто подошла."]),
    (11.8, 15.4, ["Любовь — это когда", "один зонт на двоих"]),
    (15.6, 19.6, ["…и дождь", "заканчивается"]),
]


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, a, b):
    return clamp((t - a) / (b - a))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def back(x):
    x = clamp(x)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def lerp(a, b, k):
    return a + (b - a) * k


def mix(c1, c2, k):
    return tuple(lerp(a, b, k) for a, b in zip(c1, c2))


def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# ---------- статичные слои ----------
rng = random.Random(7)
BUILDINGS = []
x = -40
while x < W + 40:
    bw = rng.randint(110, 210)
    bh = rng.randint(380, 820)
    wins = [(wx, wy, rng.random() < 0.38)
            for wx in range(x + 18, x + bw - 30, 42)
            for wy in range(GROUND - bh + 30, GROUND - 60, 56)]
    BUILDINGS.append((x, bw, bh, wins))
    x += bw + rng.randint(4, 20)

STARS = [(rng.uniform(0, W), rng.uniform(80, 900), rng.uniform(1.5, 4), rng.uniform(0, 6.28))
         for _ in range(140)]
DROPS = [(rng.uniform(-200, W + 200), rng.uniform(0, H), rng.uniform(1700, 2400), rng.uniform(40, 80))
         for _ in range(420)]
HEARTS = [(rng.uniform(0, 6.283), rng.uniform(380, 900), rng.uniform(30, 75), rng.uniform(-3, 3),
           rng.choice(["#FF4D6D", "#FF8FA3", "#FFB3C1", "#FFD166", "#FFFFFF"]))
          for _ in range(46)]


def city_layer():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    for (bx, bw, bh, wins) in BUILDINGS:
        c.set_source_rgb(*hexc("#141833"))
        c.rectangle(bx, GROUND - bh, bw, bh)
        c.fill()
        for wx, wy, on in wins:
            if on:
                c.set_source_rgba(1.0, 0.82, 0.45, 0.85)
            else:
                c.set_source_rgba(0.25, 0.28, 0.45, 0.6)
            c.rectangle(wx, wy, 22, 30)
            c.fill()
    return s


CITY = city_layer()


# ---------- примитивы ----------
def heart_path(c, cx, cy, s):
    r = s * 0.27
    c.new_path()
    c.move_to(cx, cy + s * 0.5)
    c.arc(cx - s * 0.245, cy - s * 0.15, r, math.pi * 0.75, math.pi * 2)
    c.arc(cx + s * 0.245, cy - s * 0.15, r, math.pi, math.pi * 2.25)
    c.close_path()


def ellipse(c, cx, cy, rx, ry):
    c.save()
    c.translate(cx, cy)
    c.scale(rx, ry)
    c.arc(0, 0, 1, 0, 2 * math.pi)
    c.restore()


def blink(t, seed):
    p = (t + seed) % 3.3
    return 0.1 if p < 0.12 else 1.0


def draw_char(c, x, y, body_col, t, look=(0, 0), mood=-0.6, blush=0.0, bow=False,
              lhand=None, rhand=None, squash=1.0, seed=0.0):
    """y — уровень земли. look: (-1..1, -1..1) направление взгляда."""
    lw, cy = 88, y - 165
    # ноги
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_source_rgb(*mix(body_col, (0, 0, 0), 0.35))
    c.set_line_width(16)
    for dx in (-34, 34):
        c.move_to(x + dx, y - 70)
        c.line_to(x + dx, y - 12)
        c.stroke()
        ellipse(c, x + dx + 6 * (1 if dx > 0 else -1), y - 8, 22, 11)
        c.fill()
    # руки
    sh_l, sh_r = (x - 74, cy + 20), (x + 74, cy + 20)
    lhand = lhand or (x - 98, cy + 110)
    rhand = rhand or (x + 98, cy + 110)
    c.set_line_width(15)
    for sh, hd in ((sh_l, lhand), (sh_r, rhand)):
        c.move_to(*sh)
        mx, my = (sh[0] + hd[0]) / 2, (sh[1] + hd[1]) / 2 + 18
        c.curve_to(mx, my, mx, my, *hd)
        c.stroke()
        c.arc(hd[0], hd[1], 13, 0, 2 * math.pi)
        c.fill()
    # тело
    c.save()
    c.translate(x, y - 70)
    c.scale(1 / squash ** 0.5, squash)
    c.translate(0, -95)
    g = cairo.LinearGradient(0, -120, 0, 120)
    g.add_color_stop_rgb(0, *mix(body_col, (1, 1, 1), 0.25))
    g.add_color_stop_rgb(1, *mix(body_col, (0, 0, 0), 0.12))
    c.set_source(g)
    ellipse(c, 0, 0, lw, 118)
    c.fill()
    c.restore()
    # бантик
    if bow:
        bx, by = x + 30, cy - 112 * squash
        c.set_source_rgb(*hexc("#FFD166"))
        for sgn in (-1, 1):
            c.move_to(bx, by)
            c.line_to(bx + sgn * 38, by - 22)
            c.line_to(bx + sgn * 38, by + 20)
            c.close_path()
            c.fill()
        c.arc(bx, by, 10, 0, 2 * math.pi)
        c.fill()
    # лицо
    ex, ey = look[0] * 12, look[1] * 9
    fy = cy - 35 * squash
    b = blink(t, seed)
    for dx in (-30, 30):
        c.set_source_rgb(1, 1, 1)
        ellipse(c, x + dx + ex * 0.6, fy, 24, 28 * b)
        c.fill()
        if b > 0.5:
            c.set_source_rgb(*hexc("#1B1B2F"))
            c.arc(x + dx + ex * 1.2, fy + ey + 3, 12, 0, 2 * math.pi)
            c.fill()
            c.set_source_rgb(1, 1, 1)
            c.arc(x + dx + ex * 1.2 + 4, fy + ey - 2, 4, 0, 2 * math.pi)
            c.fill()
    # румянец
    if blush > 0:
        c.set_source_rgba(1, 0.35, 0.45, 0.55 * blush)
        for dx in (-52, 52):
            ellipse(c, x + dx + ex * 0.5, fy + 38, 17, 9)
            c.fill()
    # рот
    mx, my = x + ex * 0.6, fy + 50
    c.set_source_rgb(*hexc("#1B1B2F"))
    c.set_line_width(6)
    c.move_to(mx - 20, my)
    c.curve_to(mx - 8, my + 22 * mood, mx + 8, my + 22 * mood, mx + 20, my)
    c.stroke()


def draw_umbrella(c, hx, hy, openk, tilt=0.0, length=290):
    """hx, hy — рука, держащая ручку."""
    c.save()
    c.translate(hx, hy)
    c.rotate(tilt)
    top = -length
    wdt = lerp(26, 210, openk)
    hgt = lerp(150, 120, openk)
    # ручка
    c.set_source_rgb(*hexc("#5B3A29"))
    c.set_line_width(9)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.move_to(0, top + 10)
    c.line_to(0, 10)
    c.arc_negative(-16, 10, 16, 0, math.pi)
    c.stroke()
    # купол
    g = cairo.LinearGradient(-wdt, 0, wdt, 0)
    g.add_color_stop_rgb(0, *hexc("#FFC233"))
    g.add_color_stop_rgb(1, *hexc("#FF9F1C"))
    c.set_source(g)
    c.move_to(-wdt, top + 6)
    c.curve_to(-wdt, top - hgt, wdt, top - hgt, wdt, top + 6)
    n = 4
    for i in range(n):
        x0 = wdt - (2 * wdt) * i / n
        x1 = wdt - (2 * wdt) * (i + 1) / n
        c.curve_to(x0, top - 22 * openk, x1, top - 22 * openk, x1, top + 6)
    c.close_path()
    c.fill()
    # спицы
    c.set_source_rgba(1, 1, 1, 0.35 * openk)
    c.set_line_width(3)
    for i in range(1, n):
        xx = wdt - (2 * wdt) * i / n
        c.move_to(0, top - hgt * 0.75)
        c.line_to(xx, top - 8)
        c.stroke()
    c.set_source_rgb(*hexc("#5B3A29"))
    c.arc(0, top - hgt * 0.76, 7, 0, 2 * math.pi)
    c.fill()
    c.restore()
    # вернуть зону укрытия от дождя в мировых координатах
    return (hx + math.sin(tilt) * length, hy - math.cos(tilt) * length, wdt)


def text_block(c, lines, cx, cy, size, alpha, color=(1, 1, 1), stroke=(0.07, 0.05, 0.15)):
    if alpha <= 0:
        return
    c.select_font_face("Inter Display", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    c.set_font_size(size)
    lh = size * 1.18
    y0 = cy - lh * (len(lines) - 1) / 2
    for i, ln in enumerate(lines):
        ext = c.text_extents(ln)
        tx = cx - ext.width / 2 - ext.x_bearing
        ty = y0 + i * lh + size * 0.35
        c.move_to(tx, ty)
        c.text_path(ln)
        c.set_source_rgba(*stroke, 0.85 * alpha)
        c.set_line_width(size * 0.16)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.stroke_preserve()
        c.set_source_rgba(*color, alpha)
        c.fill()


# ---------- кадр ----------
def frame(t):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    clear = ease(prog(t, CLEAR0, CLEAR1))
    rain = 1 - ease(prog(t, CLEAR0 - 0.3, CLEAR1 - 0.6))

    # лёгкий наезд камеры на кульминации
    zoom = 1 + 0.07 * ease(prog(t, HEART0, POP)) - 0.03 * ease(prog(t, POP, POP + 1.5))
    c.save()
    c.translate(W / 2, 1150)
    c.scale(zoom, zoom)
    c.translate(-W / 2, -1150)

    # небо
    g = cairo.LinearGradient(0, 0, 0, GROUND)
    g.add_color_stop_rgb(0, *mix(hexc("#070B22"), hexc("#3A2A7A"), clear))
    g.add_color_stop_rgb(0.6, *mix(hexc("#1B2048"), hexc("#B05A9E"), clear))
    g.add_color_stop_rgb(1, *mix(hexc("#2C3263"), hexc("#FFB38A"), clear))
    c.set_source(g)
    c.rectangle(-100, -100, W + 200, H + 200)
    c.fill()

    # звёзды и луна
    if clear > 0:
        for sx, sy, sr, ph in STARS:
            a = clear * (0.5 + 0.5 * math.sin(t * 3 + ph))
            c.set_source_rgba(1, 1, 0.9, a)
            c.arc(sx, sy, sr, 0, 2 * math.pi)
            c.fill()
        mx, my = 800, lerp(760, 470, clear)
        rg = cairo.RadialGradient(mx, my, 40, mx, my, 260)
        rg.add_color_stop_rgba(0, 1, 0.95, 0.8, 0.45 * clear)
        rg.add_color_stop_rgba(1, 1, 0.95, 0.8, 0)
        c.set_source(rg)
        c.arc(mx, my, 260, 0, 2 * math.pi)
        c.fill()
        c.set_source_rgba(1, 0.97, 0.86, clear)
        c.arc(mx, my, 85, 0, 2 * math.pi)
        c.fill()

    # тучи
    cloud_a = 0.85 * (1 - clear)
    if cloud_a > 0:
        for i in range(6):
            cx0 = (i * 260 + t * 18 - 150) % (W + 400) - 200
            off = -clear * 500
            c.set_source_rgba(0.16, 0.17, 0.3, cloud_a)
            for dx, dy, r in ((0, 0, 110), (100, -40, 120), (210, 0, 100)):
                c.arc(cx0 + dx, 140 + (i % 2) * 90 + dy + off, r, 0, 2 * math.pi)
                c.fill()

    # город
    c.set_source_surface(CITY, 0, 0)
    c.paint_with_alpha(0.9)

    # земля
    gg = cairo.LinearGradient(0, GROUND, 0, H)
    gg.add_color_stop_rgb(0, *mix(hexc("#22263F"), hexc("#5B3C68"), clear))
    gg.add_color_stop_rgb(1, *mix(hexc("#0E1020"), hexc("#2E1F3D"), clear))
    c.set_source(gg)
    c.rectangle(-100, GROUND, W + 200, H - GROUND + 100)
    c.fill()
    # лужи
    for px, py, pr in ((180, 1640, 150), (760, 1720, 210), (430, 1820, 120)):
        c.set_source_rgba(*mix((0.45, 0.55, 0.95), (1.0, 0.75, 0.6), clear), 0.22)
        ellipse(c, px, py, pr, pr * 0.16)
        c.fill()

    # фонарь
    lx = 170
    c.set_source_rgb(*hexc("#0B0D1A"))
    c.rectangle(lx - 9, 880, 18, GROUND - 880)
    c.fill()
    c.rectangle(lx - 40, 860, 80, 26)
    c.fill()
    lamp_a = 0.9 - 0.4 * clear
    rg = cairo.RadialGradient(lx, 900, 10, lx, 900, 420)
    rg.add_color_stop_rgba(0, 1, 0.85, 0.5, 0.55 * lamp_a)
    rg.add_color_stop_rgba(1, 1, 0.85, 0.5, 0)
    c.set_source(rg)
    c.arc(lx, 900, 420, 0, 2 * math.pi)
    c.fill()
    c.move_to(lx - 30, 900)
    c.line_to(lx + 30, 900)
    c.line_to(lx + 330, GROUND)
    c.line_to(lx - 270, GROUND)
    c.close_path()
    lg = cairo.LinearGradient(0, 900, 0, GROUND)
    lg.add_color_stop_rgba(0, 1, 0.85, 0.5, 0.22 * lamp_a)
    lg.add_color_stop_rgba(1, 1, 0.85, 0.5, 0.04 * lamp_a)
    c.set_source(lg)
    c.fill()
    c.set_source_rgb(1, 0.9, 0.6)
    ellipse(c, lx, 896, 26, 14)
    c.fill()

    # ---- персонажи ----
    BLUE, PINK = hexc("#4D7CFE"), hexc("#FF6F91")
    hx = 400 + (math.sin(t * 38) * 2.5 if t < SHARE1 else 0)  # дрожит, пока мокнет
    walk = ease(prog(t, WALK0, WALK1))
    sx = lerp(1260, 690, walk)
    sy = GROUND
    if WALK0 <= t < WALK1:
        sy -= abs(math.sin(math.pi * (t - WALK0) / STEP)) * 16

    # сердцебиение — лёгкий «пульс» тел
    pulse = 0.0
    for bt in BEATS:
        if bt <= t < bt + 0.25:
            pulse = math.sin(math.pi * (t - bt) / 0.25)
    sq = 1 + 0.03 * pulse + 0.012 * math.sin(t * 2.4)

    he_look_x = lerp(-0.2, 1.0, ease(prog(t, 6.5, 7.5)))
    he_look_y = lerp(0.8, -0.2, ease(prog(t, 6.5, 7.5)))
    she_look_x = lerp(-0.4, -1.0, ease(prog(t, 7.5, 8.3)))
    he_mood = lerp(-0.7, 0.9, ease(prog(t, 12.0, 13.5)))
    she_mood = lerp(0.2, 1.0, ease(prog(t, 10.0, 12.0)))
    blush = ease(prog(t, 8.5, 11.0))

    hold = ease(prog(t, HANDS, HANDS + 0.8))
    meet = ((hx + sx) / 2, GROUND - 120)
    he_r = (lerp(hx + 98, meet[0], hold), lerp(GROUND - 55, meet[1], hold))

    # рука с зонтом
    share = ease(prog(t, SHARE0, SHARE1))
    closek = ease(prog(t, CLOSE0, CLOSE1))
    u_hand = (lerp(sx + 95, (hx + sx) / 2 + 30, share), lerp(GROUND - 250, GROUND - 270, share))
    u_hand = (lerp(u_hand[0], sx + 100, closek), lerp(u_hand[1], GROUND - 100, closek))
    tilt = lerp(-0.08, -0.04, share) + 0.05 * math.sin(t * 1.3)
    tilt = lerp(tilt, 0.12, closek)
    she_l = (lerp(sx - 98, meet[0], hold), lerp(GROUND - 55, meet[1], hold))

    # капли с него, пока он мокнет
    if t < SHARE1:
        wet = 1 - share
        for k in range(5):
            ph = (t * 1.4 + k * 0.37) % 1
            c.set_source_rgba(0.6, 0.75, 1, 0.8 * wet)
            ellipse(c, W / 2 + (hx - 70 + k * 35 - W / 2) * 1.3, GROUND - (260 - ph * 260) * 1.3, 5, 11)
            c.fill()

    CS = 1.3  # крупнее персонажей — на телефоне должны читаться лица
    c.save()
    c.translate(W / 2, GROUND)
    c.scale(CS, CS)
    c.translate(-W / 2, -GROUND)
    draw_char(c, hx, GROUND, BLUE, t, (he_look_x, he_look_y), he_mood, blush,
              rhand=he_r, squash=sq, seed=0.0)
    draw_char(c, sx, sy, PINK, t, (she_look_x, -0.1), she_mood, blush, bow=True,
              lhand=she_l, rhand=u_hand, squash=sq, seed=1.3)
    ux, uy, uw = draw_umbrella(c, u_hand[0], u_hand[1], 1 - closek, tilt)
    c.restore()
    shelter = (W / 2 + (ux - W / 2) * CS, GROUND + (uy - GROUND) * CS, uw * CS)

    # дождь
    if rain > 0:
        n = int(len(DROPS) * rain)
        c.set_line_width(2.6)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        ux, uy, uw = shelter
        for i in range(n):
            x0, ph, v, ln = DROPS[i]
            y = (ph + t * v) % (H + 300) - 200
            xx = x0 + y * 0.12
            if (1 - closek) > 0.3 and abs(xx - ux) < uw and y > uy - 80 and y < GROUND:
                continue
            if y > GROUND + 380:
                continue
            c.set_source_rgba(0.7, 0.8, 1.0, 0.5)
            c.move_to(xx, y)
            c.line_to(xx - ln * 0.12, y - ln)
            c.stroke()
        # брызги
        for i in range(0, n, 6):
            x0, ph, v, _ = DROPS[i]
            k = ((ph + t * v) / 380) % 1
            c.set_source_rgba(0.75, 0.85, 1, 0.5 * (1 - k))
            ellipse(c, x0, GROUND + 30 + (i % 7) * 50, 6 + 26 * k, 2 + 5 * k)
            c.stroke()

    # растущее сердце и взрыв сердечек
    if HEART0 <= t < POP:
        k = prog(t, HEART0, POP)
        hy = lerp(meet[1] - 40, 760, ease(k))
        hs = lerp(30, 300, back(k)) * (1 + 0.06 * math.sin(t * 14))
        glow = cairo.RadialGradient(meet[0], hy, 0, meet[0], hy, hs * 1.4)
        glow.add_color_stop_rgba(0, 1, 0.4, 0.55, 0.45)
        glow.add_color_stop_rgba(1, 1, 0.4, 0.55, 0)
        c.set_source(glow)
        c.arc(meet[0], hy, hs * 1.4, 0, 2 * math.pi)
        c.fill()
        heart_path(c, meet[0], hy, hs)
        hg = cairo.LinearGradient(0, hy - hs / 2, 0, hy + hs / 2)
        hg.add_color_stop_rgb(0, *hexc("#FF758F"))
        hg.add_color_stop_rgb(1, *hexc("#E5383B"))
        c.set_source(hg)
        c.fill()
        heart_path(c, meet[0] - hs * 0.15, hy - hs * 0.12, hs * 0.22)
        c.set_source_rgba(1, 1, 1, 0.45)
        c.fill()
    if t >= POP:
        k = prog(t, POP, POP + 3.2)
        for ang, dist, sz, spin, col in HEARTS:
            d = dist * (1 - (1 - k) ** 3)
            px = meet[0] + math.cos(ang) * d
            py = 760 + math.sin(ang) * d + 420 * k * k
            c.save()
            c.translate(px, py)
            c.rotate(spin * k)
            heart_path(c, 0, 0, sz * (1 - 0.4 * k))
            c.set_source_rgba(*hexc(col), 1 - k)
            c.fill()
            c.restore()
        # вспышка
        fa = 1 - prog(t, POP, POP + 0.5)
        if fa > 0:
            c.set_source_rgba(1, 0.9, 0.95, 0.6 * fa)
            c.rectangle(-100, -100, W + 200, H + 200)
            c.fill()

    c.restore()

    # подписи
    for a, b, lines in CAPTIONS:
        if a - 0.1 <= t <= b + 0.1:
            k_in, k_out = ease(prog(t, a, a + 0.35)), 1 - ease(prog(t, b - 0.3, b))
            al = min(k_in, k_out)
            text_block(c, lines, W / 2, 420 + 24 * (1 - k_in), 74, al)

    # финальная карточка
    if t >= END0:
        k = ease(prog(t, END0, END0 + 0.9))
        g = cairo.LinearGradient(0, 0, 0, H)
        g.add_color_stop_rgba(0, *hexc("#FF4D6D"), 0.92 * k)
        g.add_color_stop_rgba(1, *hexc("#7B2CBF"), 0.92 * k)
        c.set_source(g)
        c.rectangle(0, 0, W, H)
        c.fill()
        beat = 1 + 0.08 * max(0.0, math.sin((t - END0) * math.pi * 2 / 0.75)) ** 6
        hs = 330 * back(prog(t, END0 + 0.2, END0 + 1.0)) * beat
        if hs > 1:
            heart_path(c, W / 2, 820, hs)
            c.set_source_rgba(1, 1, 1, k)
            c.fill()
            # жёлтый зонтик внутри сердца
            c.save()
            c.translate(W / 2, 845)
            c.scale(hs / 330, hs / 330)
            c.set_source_rgba(*hexc("#FFB703"), k)
            c.move_to(-90, 0)
            c.curve_to(-90, -110, 90, -110, 90, 0)
            for i in range(3):
                x0, x1 = 90 - 60 * i, 30 - 60 * i
                c.curve_to(x0, -14, x1, -14, x1, 0)
            c.close_path()
            c.fill()
            c.set_source_rgba(*hexc("#5B3A29"), k)
            c.set_line_width(7)
            c.move_to(0, 0)
            c.line_to(0, 90)
            c.arc_negative(-13, 90, 13, 0, math.pi)
            c.stroke()
            c.restore()
        ta = ease(prog(t, END0 + 0.6, END0 + 1.3))
        text_block(c, ["Отправь тому,", "с кем делишь", "один зонт"], W / 2, 1290, 92, ta,
                   stroke=(0.35, 0.05, 0.25))
        ta2 = ease(prog(t, END0 + 1.4, END0 + 2.0))
        text_block(c, ["пусть знает"], W / 2, 1570, 64, ta2,
                   color=hexc("#FFE5EC"), stroke=(0.35, 0.05, 0.25))

    # виньетка
    vg = cairo.RadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.75)
    vg.add_color_stop_rgba(0, 0, 0, 0, 0)
    vg.add_color_stop_rgba(1, 0, 0, 0, 0.45)
    c.set_source(vg)
    c.paint()
    # плавный вход из черного
    fi = 1 - prog(t, 0, 0.6)
    if fi > 0:
        c.set_source_rgba(0, 0, 0, fi)
        c.paint()
    s.flush()
    return bytes(s.get_data())


# ---------- звук ----------
def synth_audio(path):
    n = int(SR * DUR)
    tt = np.arange(n) / SR
    L = np.zeros(n)
    R = np.zeros(n)
    rs = np.random.default_rng(3)

    def env_curve(points):
        xs, ys = zip(*points)
        return np.interp(tt, xs, ys)

    def add(sig, start, gain=1.0, pan=0.0):
        i0 = int(start * SR)
        if i0 >= n:
            return
        sig = sig[: n - i0]
        L[i0:i0 + len(sig)] += sig * gain * (1 - pan) / 2 * 2 ** 0.5
        R[i0:i0 + len(sig)] += sig * gain * (1 + pan) / 2 * 2 ** 0.5

    def bandnoise(length, lo, hi):
        x = rs.standard_normal(length)
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(length, 1 / SR)
        X[(f < lo) | (f > hi)] = 0
        y = np.fft.irfft(X, length)
        return y / (np.abs(y).max() + 1e-9)

    # дождь: шум + отдельные капли, затихает вместе с картинкой
    rain_env = env_curve([(0, 0), (0.6, 1), (CLEAR0 - 0.3, 1), (CLEAR1 - 0.4, 0), (DUR, 0)])
    rainL = bandnoise(n, 400, 7000) * 0.16
    rainR = bandnoise(n, 400, 7000) * 0.16
    rumble = bandnoise(n, 40, 250) * 0.10
    L += (rainL + rumble) * rain_env
    R += (rainR + rumble) * rain_env
    for _ in range(int(DUR * 25)):
        st = rs.uniform(0, CLEAR1)
        ln = int(SR * 0.02)
        d = rs.standard_normal(ln) * np.exp(-np.arange(ln) / (SR * 0.003))
        add(d * float(np.interp(st, tt, rain_env)), st, 0.18, rs.uniform(-0.8, 0.8))
    # стук капель по зонту (пока он открыт)
    for _ in range(140):
        st = rs.uniform(WALK0, CLOSE0)
        ln = int(SR * 0.03)
        e = np.exp(-np.arange(ln) / (SR * 0.004))
        f = rs.uniform(1800, 2600)
        add(np.sin(2 * np.pi * f * np.arange(ln) / SR) * e, st,
            0.07 * float(np.interp(st, tt, rain_env)), 0.3)

    # шаги по лужам
    for i, st in enumerate(STEPS):
        ln = int(SR * 0.16)
        k = np.arange(ln) / SR
        thump = np.sin(2 * np.pi * 85 * k) * np.exp(-k / 0.03)
        splash = bandnoise(ln, 1500, 6000) * np.exp(-k / 0.05)
        pan = lerp(0.8, 0.2, (st - WALK0) / (WALK1 - WALK0))
        add(thump * 0.5 + splash * 0.25, st, 0.6, pan)

    # сердцебиение
    for bt in BEATS:
        for off, g in ((0.0, 1.0), (0.2, 0.7)):
            ln = int(SR * 0.18)
            k = np.arange(ln) / SR
            fr = 60 - 25 * k / 0.18
            ph = 2 * np.pi * np.cumsum(fr) / SR
            add(np.sin(ph) * np.exp(-k / 0.05), bt + off, 0.9 * g)

    # музыка: мягкий пэд + «музыкальная шкатулка»
    def midi(m):
        return 440 * 2 ** ((m - 69) / 12)

    chords = [[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59],
              [48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [48, 55, 60, 64]]
    clen = DUR / len(chords)
    music_env = env_curve([(0, 0.35), (WALK0, 0.55), (CLEAR0, 0.7), (CLEAR1, 1.0),
                           (DUR - 1.5, 1.0), (DUR, 0)])
    pad = np.zeros(n)
    for ci, ch in enumerate(chords):
        a, b = int(ci * clen * SR), int((ci + 1) * clen * SR + SR * 0.5)
        b = min(b, n)
        k = np.arange(b - a) / SR
        e = np.minimum(1, k / 0.8) * np.minimum(1, (b - a) / SR - k)
        for m in ch:
            f = midi(m)
            pad[a:b] += (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(2 * np.pi * 2 * f * k + 0.5)) * e * 0.035
    L += pad * music_env
    R += pad * music_env

    def bell(f, length=1.4):
        ln = int(SR * length)
        k = np.arange(ln) / SR
        s = (np.sin(2 * np.pi * f * k) * np.exp(-k / 0.5)
             + 0.45 * np.sin(2 * np.pi * 2.0 * f * k) * np.exp(-k / 0.25)
             + 0.2 * np.sin(2 * np.pi * 3.01 * f * k) * np.exp(-k / 0.12))
        return s * np.minimum(1, k / 0.004)

    pattern = [0, 1, 2, 3, 2, 1, 2, 3]
    step = clen / 8
    for ci, ch in enumerate(chords):
        notes = [m + 24 for m in ch]
        for j, p in enumerate(pattern):
            st = ci * clen + j * step
            if ci == len(chords) - 1 and j > 3:
                break
            m = notes[p] + (12 if (ci >= 4 and j in (3, 7)) else 0)
            g = 0.10 * float(np.interp(st, tt, music_env))
            add(bell(midi(m)), st, g, 0.35 if j % 2 else -0.35)
    # финальный аккорд
    for m in (72, 76, 79, 84):
        add(bell(midi(m), 3.0), DUR - 3.2, 0.09, 0)

    # «волшебный» глиссандо, когда кончается дождь
    for i, m in enumerate([72, 74, 76, 79, 81, 84, 86, 88, 91, 93]):
        add(bell(midi(m), 0.9), CLEAR0 + 0.4 + i * 0.07, 0.07, -0.6 + i * 0.13)
    # нарастание к взрыву сердца
    ln = int(SR * (POP - HEART0))
    k = np.arange(ln) / SR
    fr = 200 + 700 * (k / k[-1]) ** 2
    riser = np.sin(2 * np.pi * np.cumsum(fr) / SR) * (k / k[-1]) ** 2 * 0.25
    riser += bandnoise(ln, 2000, 9000) * (k / k[-1]) ** 3 * 0.08
    add(riser, HEART0, 1.0)
    # «пух!»
    ln = int(SR * 0.5)
    k = np.arange(ln) / SR
    pop = np.sin(2 * np.pi * np.cumsum(300 + 900 * np.exp(-k / 0.03)) / SR) * np.exp(-k / 0.08)
    pop += bandnoise(ln, 3000, 12000) * np.exp(-k / 0.06) * 0.4
    add(pop, POP, 0.7)
    for i in range(16):
        add(bell(midi(84 + (i * 5) % 14), 0.6), POP + 0.05 + i * 0.06, 0.05,
            math.sin(i * 1.7) * 0.8)
    # «бум» сердца на финальной карточке
    for j in range(7):
        bt = END0 + 0.2 + j * 0.75
        ln = int(SR * 0.2)
        k = np.arange(ln) / SR
        add(np.sin(2 * np.pi * np.cumsum(70 - 30 * k / 0.2) / SR) * np.exp(-k / 0.05), bt, 0.5)

    mixd = np.stack([L, R], axis=1)
    fade = np.ones(n)
    fade[-int(SR * 0.8):] = np.linspace(1, 0, int(SR * 0.8))
    mixd *= fade[:, None]
    mixd /= np.abs(mixd).max() / 0.89
    pcm = (mixd * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    wav = os.path.join(TMP, "love_umbrella.wav")
    synth_audio(wav)
    if "--still" in sys.argv:
        for ts in map(float, sys.argv[sys.argv.index("--still") + 1:]):
            data = frame(ts)
            surf = cairo.ImageSurface.create_for_data(bytearray(data), cairo.FORMAT_ARGB32, W, H)
            surf.write_to_png(os.path.join(TMP, f"still_{ts:05.1f}.png"))
        return
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", wav,
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", OUT,
    ], stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    for i in range(total):
        ff.stdin.write(frame(i / FPS))
        if i % 90 == 0:
            print(f"кадр {i}/{total}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("готово:", OUT)


if __name__ == "__main__":
    main()
