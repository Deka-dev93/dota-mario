"""Dota Mario - платформер в духе Марио с героями в стиле Доты.

Герои: Pudge, Invoker, Meepo, Earthshaker. Карта мира с дорогой между уровнями, магазин,
Aghanim's Shard (как гриб в Марио), жизни и монеты, музыка. Вся графика и звук рисуются кодом.

Запуск:  py game.py   (нужен pygame-ce:  py -m pip install pygame-ce)
Свою музыку можно положить в папку music рядом с игрой: level.mp3 / map.mp3 / boss.mp3 (или .ogg/.wav).

Фан-проект. Dota 2 и её персонажи принадлежат Valve; здесь нет файлов из игры,
все рисунки нарисованы кодом заново.
"""
import array
import json
import math
import os
import random
import sys
import textwrap

import pygame

SW, SH = 960, 540
T = 36
ROWS = 15
FPS = 60
GRAV = 0.6
MAXFALL = 15.0

pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.init()
pygame.display.set_caption("Dota Mario")


# ----------------------------------------------- слой высокого разрешения ----
# Игра считает всё в "логических" координатах 960x540, а рисует в K раз крупнее
# (K=2 -> 1920x1080). Слой D и класс HS сами умножают координаты на K, поэтому
# остальной код про разрешение ничего не знает, а картинка получается чёткой.
K = 2.0
_cache_clearers = []


def set_scale(k):
    global K
    K = float(k)
    for fn in _cache_clearers:
        fn()


def rw():
    return max(1, int(round(SW * K)))


def rh():
    return max(1, int(round(SH * K)))


def _r(v):
    return int(round(v * K))


class HS:
    """Поверхность высокого разрешения с логическими размерами."""

    def __init__(self, w, h, alpha=False, surf=None):
        if surf is None:
            size = (max(1, _r(w)), max(1, _r(h)))
            surf = pygame.Surface(size, pygame.SRCALPHA) if alpha else pygame.Surface(size)
            if pygame.display.get_surface() is not None:
                surf = surf.convert_alpha() if alpha else surf.convert()
        self.surf = surf
        self.lw, self.lh = w, h

    def get_width(self):
        return self.lw

    def get_height(self):
        return self.lh

    def get_size(self):
        return (self.lw, self.lh)

    def get_rect(self, **kw):
        r = pygame.Rect(0, 0, int(round(self.lw)), int(round(self.lh)))
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    def blit(self, src, pos=(0, 0), area=None, special_flags=0):
        s = src.surf if isinstance(src, HS) else src
        self.surf.blit(s, (_r(pos[0]), _r(pos[1])), area, special_flags)

    def fill(self, color, rect=None, special_flags=0):
        if rect is not None:
            rect = pygame.Rect(_r(rect[0]), _r(rect[1]), max(1, _r(rect[2])), max(1, _r(rect[3])))
        self.surf.fill(color, rect, special_flags)

    def set_at(self, pos, color):
        self.surf.fill(color, (_r(pos[0]), _r(pos[1]), max(1, _r(1)), max(1, _r(1))))

    def set_alpha(self, a):
        self.surf.set_alpha(a)

    def set_colorkey(self, c):
        self.surf.set_colorkey(c)


def HSurf(size, flags=0):
    return HS(size[0], size[1], alpha=bool(flags & pygame.SRCALPHA))


def _t(s):
    return s.surf if isinstance(s, HS) else s


class _Draw:
    """pygame.draw с автоматическим масштабированием координат, толщины и радиусов."""

    @staticmethod
    def _rect(rect):
        return pygame.Rect(_r(rect[0]), _r(rect[1]), max(1, _r(rect[2])), max(1, _r(rect[3])))

    @staticmethod
    def _w(width):
        return max(1, _r(width)) if width else 0

    @staticmethod
    def _pts(pts):
        return [(p[0] * K, p[1] * K) for p in pts]

    def rect(self, s, color, rect, width=0, border_radius=0, **kw):
        pygame.draw.rect(_t(s), color, self._rect(rect), self._w(width), border_radius=_r(border_radius))

    def circle(self, s, color, center, radius, width=0, **kw):
        pygame.draw.circle(_t(s), color, (center[0] * K, center[1] * K), max(1, radius * K), self._w(width))

    def ellipse(self, s, color, rect, width=0):
        pygame.draw.ellipse(_t(s), color, self._rect(rect), self._w(width))

    def polygon(self, s, color, pts, width=0):
        pygame.draw.polygon(_t(s), color, self._pts(pts), self._w(width))

    def line(self, s, color, a, b, width=1):
        pygame.draw.line(_t(s), color, (a[0] * K, a[1] * K), (b[0] * K, b[1] * K), self._w(width) or 1)

    def lines(self, s, color, closed, pts, width=1):
        pygame.draw.lines(_t(s), color, closed, self._pts(pts), self._w(width) or 1)

    def arc(self, s, color, rect, start, stop, width=1):
        pygame.draw.arc(_t(s), color, self._rect(rect), start, stop, self._w(width) or 1)


D = _Draw()


def t_flip(hs, fx, fy):
    return HS(hs.lw, hs.lh, surf=pygame.transform.flip(hs.surf, fx, fy))


def t_scale(hs, size):
    """Масштабирование к логическому размеру size."""
    return HS(size[0], size[1], surf=pygame.transform.smoothscale(hs.surf, (max(1, _r(size[0])), max(1, _r(size[1])))))


_fonts = {}
_cache_clearers.append(_fonts.clear)


class HFont:
    """Шрифт в логических пикселях: отрисовывается чётко в разрешении K."""

    def __init__(self, size, bold=False):
        self.size, self.bold = size, bold

    def _font(self):
        key = (self.size, self.bold, K)
        f = _fonts.get(key)
        if f is None:
            f = pygame.font.SysFont("segoeui,arial,tahoma,dejavusans", max(6, int(round(self.size * K))), bold=self.bold)
            _fonts[key] = f
        return f

    def render(self, msg, aa, color):
        surf = self._font().render(msg, True, color)
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        return HS(surf.get_width() / K, surf.get_height() / K, surf=surf)


def font(size, bold=False):
    return HFont(size, bold)


F_XS, F_S, F_M, F_L, F_XL = font(12), font(15), font(21, True), font(38, True), font(62, True)


def res_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def save_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DotaMario")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


# ----------------------------------------------------------------- звук -----
SOUNDS = {}


def tone_buf(freq, ms, vol=0.25, kind="square", slide=0.0):
    n = int(22050 * ms / 1000)
    buf = array.array("h")
    for i in range(n):
        f = max(30.0, freq + slide * i / n)
        ph = (i * f / 22050) % 1
        v = (1 if ph < 0.5 else -1) if kind == "square" else math.sin(2 * math.pi * ph)
        buf.append(int(v * vol * (1 - i / n) * 32767))
    return buf


def snd(*parts):
    buf = array.array("h")
    for p in parts:
        buf.extend(p)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def init_sounds():
    if not pygame.mixer.get_init():
        return
    try:
        SOUNDS["jump"] = snd(tone_buf(380, 110, 0.16, "square", 320))
        SOUNDS["coin"] = snd(tone_buf(900, 70, 0.16, "square", 0), tone_buf(1350, 120, 0.16, "square", 0))
        SOUNDS["hit"] = snd(tone_buf(170, 230, 0.28, "square", -120))
        SOUNDS["stomp"] = snd(tone_buf(240, 110, 0.22, "square", -120))
        SOUNDS["hook"] = snd(tone_buf(260, 150, 0.18, "sine", 260))
        SOUNDS["boom"] = snd(tone_buf(110, 320, 0.32, "square", -80))
        SOUNDS["magic"] = snd(tone_buf(500, 200, 0.16, "sine", 500))
        SOUNDS["win"] = snd(*[tone_buf(f, 140, 0.18, "square") for f in (523, 659, 784, 1047)])
        SOUNDS["bump"] = snd(tone_buf(130, 90, 0.3, "square", -40))
        SOUNDS["shard"] = snd(*[tone_buf(f, 90, 0.18, "sine") for f in (440, 554, 659, 880, 1109)])
        SOUNDS["oneup"] = snd(*[tone_buf(f, 100, 0.18, "square") for f in (660, 784, 1319, 1175, 1568)])
        SOUNDS["select"] = snd(tone_buf(700, 60, 0.15, "square", 200))
        SOUNDS["buy"] = snd(tone_buf(600, 70, 0.16, "square"), tone_buf(900, 110, 0.16, "square"))
        SOUNDS["nope"] = snd(tone_buf(160, 140, 0.2, "square", -40))
    except Exception:
        SOUNDS.clear()


def sfx(name):
    s = SOUNDS.get(name)
    if s:
        s.set_volume(0.55)
        s.play()


class Music:
    """Музыка: ищем файл music/<имя>.mp3|ogg|wav (сначала рядом с игрой, потом внутри)."""

    def __init__(self):
        self.cur = None
        self.muted = False
        self.ok = bool(pygame.mixer.get_init())
        dirs = []
        if getattr(sys, "frozen", False):
            dirs.append(os.path.join(os.path.dirname(sys.executable), "music"))
        dirs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "music"))
        dirs.append(res_path("music"))
        dirs.append(os.path.join(save_dir(), "music"))
        self.dirs = dirs

    def find(self, name):
        for ext in (".mp3", ".ogg", ".wav"):
            for d in self.dirs:
                p = os.path.join(d, name + ext)
                if os.path.isfile(p):
                    return p
        return None

    def play(self, name):
        if not self.ok or name == self.cur:
            return
        self.cur = name
        p = self.find(name)
        try:
            if p is None:
                pygame.mixer.music.stop()
                return
            pygame.mixer.music.load(p)
            pygame.mixer.music.set_volume(0.0 if self.muted else 0.55)
            pygame.mixer.music.play(-1, fade_ms=900)
        except Exception:
            self.cur = None

    def toggle(self):
        self.muted = not self.muted
        if self.ok:
            try:
                pygame.mixer.music.set_volume(0.0 if self.muted else 0.55)
            except Exception:
                pass


# ------------------------------------------------------- свет и эффекты -----
_glow = {}
_grad = {}
_vig = {}
_iris_surf = {}
for _d in (_glow, _grad, _vig, _iris_surf):
    _cache_clearers.append(_d.clear)


def add_glow(s, x, y, radius, color):
    key = (radius, color)
    g = _glow.get(key)
    if g is None:
        g = HS(radius * 2, radius * 2)
        for r in range(radius, 0, -1 if radius < 60 else -2):
            k = (1 - r / radius) ** 2
            D.circle(g, tuple(int(c * k) for c in color), (radius, radius), r)
        _glow[key] = g
    s.blit(g, (int(x - radius), int(y - radius)), special_flags=pygame.BLEND_RGB_ADD)


def gradient(c0, c1, power=1.0):
    """Вертикальный градиент на весь кадр (кэшируется)."""
    key = (c0, c1, power)
    g = _grad.get(key)
    if g is None:
        g = HS(SW, SH)
        h = rh()
        for y in range(h):
            k = (y / h) ** power
            g.surf.fill([int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3)], (0, y, rw(), 1))
        _grad[key] = g
    return g


def make_vignette():
    v = _vig.get("v")
    if v is None:
        small = pygame.Surface((48, 27), pygame.SRCALPHA)
        for y in range(27):
            for x in range(48):
                d = min(1.0, math.hypot((x - 23.5) / 24, (y - 13) / 13.5) / 1.3)
                small.set_at((x, y), (0, 0, 0, int(120 * d ** 3)))
        surf = pygame.transform.smoothscale(small, (rw(), rh()))
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        v = _vig["v"] = HS(SW, SH, surf=surf)
    return v


def bloom(s):
    """Мягкое свечение ярких мест: уменьшаем кадр, оставляем яркое, размываем и добавляем обратно."""
    src = s.surf
    w, h = src.get_size()
    small = pygame.transform.smoothscale(src, (max(8, w // 8), max(8, h // 8)))
    small.fill((150, 150, 150), special_flags=pygame.BLEND_RGB_SUB)
    small.blit(small, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    big = pygame.transform.smoothscale(small, (w, h))
    src.blit(big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def iris(s, k):
    """Круговой переход: k=0 - всё видно, k=1 - всё закрыто."""
    maxr = int(math.hypot(SW, SH) / 2) + 4
    r = int(maxr * (1 - k))
    if r <= 0:
        s.surf.fill((0, 0, 0))
        return
    if r >= maxr:
        return
    o = _iris_surf.get("o")
    if o is None:
        o = _iris_surf["o"] = pygame.Surface((rw(), rh()))
        o.set_colorkey((255, 0, 255))
    o.fill((0, 0, 0))
    pygame.draw.circle(o, (255, 0, 255), (rw() // 2, rh() // 2), int(r * K))
    s.surf.blit(o, (0, 0))


def panel(s, rect, alpha=150, radius=12, col=(14, 18, 34), border=None):
    r = pygame.Rect(rect)
    surf = HS(r.w, r.h, alpha=True)
    D.rect(surf, (*col, alpha), surf.get_rect(), border_radius=radius)
    if border:
        D.rect(surf, border, surf.get_rect(), 2, border_radius=radius)
    s.blit(surf, r.topleft)


def text(s, msg, f, col, pos, center=False, shadow=True, alpha=255):
    img = f.render(msg, True, col)
    sh = f.render(msg, True, (0, 0, 0)) if shadow else None
    if alpha < 255:
        img.set_alpha(alpha)
    if sh:
        sh.set_alpha(min(alpha, 170))
    r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    if sh:
        s.blit(sh, (r.x + 1.1, r.y + 1.1))
    s.blit(img, r)
    return r


# --------------------------------------------------------------- уровни -----
class LB:
    """Конструктор уровня: сетка символов ROWS x w."""

    def __init__(self, w):
        self.w = w
        self.g = [[" "] * w for _ in range(ROWS)]
        self.q = {}

    def ground(self, x0, x1, top=13):
        for x in range(x0, x1):
            for y in range(top, ROWS):
                self.g[y][x] = "#"

    def block(self, x, y, n=1):
        for i in range(n):
            self.g[y][x + i] = "="

    def put(self, x, y, ch):
        self.g[y][x] = ch

    def coins(self, x, y, n):
        for i in range(n):
            self.g[y][x + i] = "c"

    def qb(self, x, y, content):
        self.g[y][x] = "?"
        self.q[(x, y)] = content

    def trim(self, w):
        self.w = w
        self.g = [row[:w] for row in self.g]


def lvl1():
    b = LB(120)
    for a, c in ((0, 28), (31, 50), (53, 80), (83, 120)):
        b.ground(a, c)
    b.coins(8, 11, 4)
    b.qb(12, 9, "shard")
    b.put(14, 12, "e")
    b.block(18, 10, 4)
    b.coins(18, 9, 4)
    b.put(24, 12, "e")
    b.coins(29, 10, 2)
    b.put(34, 12, "e")
    b.block(36, 11, 3)
    b.block(40, 9, 3)
    b.put(41, 8, "+")
    b.put(45, 12, "e")
    b.put(47, 12, "e")
    b.coins(51, 10, 2)
    b.put(58, 12, "e")
    b.put(63, 12, "e")
    b.block(60, 10, 4)
    b.coins(60, 9, 4)
    b.qb(66, 9, "coins")
    b.put(70, 12, "r")
    b.coins(81, 10, 2)
    b.put(88, 12, "e")
    b.put(92, 12, "^")
    b.put(93, 12, "^")
    b.block(90, 10, 6)
    b.coins(90, 9, 6)
    b.put(100, 12, "e")
    b.put(103, 12, "r")
    b.put(112, 12, "F")
    return b


def lvl2():
    b = LB(150)
    for a, c in ((0, 20), (23, 36), (39, 52), (55, 62), (70, 92), (95, 109), (111, 150)):
        b.ground(a, c)
    b.put(10, 12, "e")
    b.qb(14, 9, "shard")
    b.put(18, 12, "r")
    b.coins(21, 10, 2)
    b.put(28, 12, "e")
    b.put(32, 12, "e")
    b.coins(37, 10, 2)
    b.put(44, 12, "r")
    b.qb(45, 9, "salve")
    b.put(47, 12, "e")
    b.put(58, 12, "e")
    b.block(63, 11, 2)
    b.block(66, 10, 2)
    b.coins(63, 10, 2)
    b.coins(66, 9, 2)
    b.put(71, 12, "+")
    for x in (76, 77):
        b.put(x, 12, "^")
    b.block(75, 10, 4)
    b.coins(75, 9, 4)
    b.put(84, 12, "e")
    b.put(89, 12, "r")
    b.coins(93, 10, 2)
    b.block(98, 10, 3)
    b.block(102, 8, 3)
    b.put(103, 7, "+")
    b.put(100, 12, "e")
    for x in (104, 105):
        b.put(x, 12, "^")
    b.coins(109, 10, 2)
    b.put(115, 12, "r")
    b.put(120, 12, "e")
    b.qb(121, 9, "coins")
    b.put(123, 12, "e")
    b.block(126, 10, 4)
    b.coins(126, 9, 4)
    b.put(128, 12, "r")
    for x in (135, 136):
        b.put(x, 12, "^")
    b.block(133, 10, 7)
    b.coins(133, 9, 7)
    b.put(141, 12, "e")
    b.put(145, 12, "r")
    b.put(147, 12, "F")
    return b


def gen_level(seed, nseg, diff):
    """Собирает уровень из проверенных проходимых кусочков: зазоры <=3, платформы <=3 клетки."""
    rnd = random.Random(seed)
    b = LB(40 + nseg * 16)
    b.ground(0, 12)
    b.coins(5, 10, 3)
    x = 12
    shard_placed = False

    def enemy(px, kind="e"):
        b.put(px, 12, kind)

    def maybe_q(qx, force=False):
        nonlocal shard_placed
        if not shard_placed:
            b.qb(qx, 9, "shard")
            shard_placed = True
        elif force or rnd.random() < 0.35:
            b.qb(qx, 9, rnd.choice(["coin", "coins", "salve"]))

    for i in range(nseg):
        kind = rnd.choice(["flat", "flat", "stairs", "pit", "spikes", "bridge", "pillars", "ambush"])
        if i == 0:
            kind = "flat"
        if kind == "flat":
            n = rnd.randint(9, 13)
            b.ground(x, x + n)
            b.coins(x + 2, 10, rnd.choice((3, 4)))
            for _ in range(1 + int(diff * rnd.random() * 1.6)):
                enemy(x + rnd.randint(3, n - 2), "r" if rnd.random() < 0.15 * diff else "e")
            maybe_q(x + n // 2 + 2)
            x += n
        elif kind == "stairs":
            n = 13
            b.ground(x, x + n)
            b.block(x + 2, 11, 3)
            b.coins(x + 2, 10, 3)
            b.block(x + 6, 9, 3)
            b.coins(x + 6, 8, 3)
            enemy(x + 11)
            enemy(x + 9, "e") if diff >= 2 else None
            x += n
        elif kind == "pit":
            g = rnd.randint(2, 3)
            b.coins(x, 10, g)
            x += g
            n = rnd.randint(7, 10)
            b.ground(x, x + n)
            enemy(x + n - 3, "r" if rnd.random() < 0.3 * diff else "e")
            x += n
        elif kind == "spikes":
            n = rnd.randint(10, 12)
            b.ground(x, x + n)
            sx = x + 4
            for k in range(2):
                b.put(sx + k, 12, "^")
            b.block(sx - 1, 10, 4)
            b.coins(sx - 1, 9, 4)
            enemy(x + n - 2)
            x += n
        elif kind == "bridge":
            g = rnd.randint(7, 9)
            px, row = x + 1, 11
            while px + 2 < x + g:
                b.block(px, row, 2)
                b.coins(px, row - 1, 2)
                px += 3
            x += g
            n = 7
            b.ground(x, x + n)
            x += n
        elif kind == "pillars":
            n = 15
            b.ground(x, x + n)
            for off, hgt in ((3, 1), (7, 2), (11, 1)):
                for hh in range(hgt):
                    b.put(x + off, 12 - hh, "=")
                b.put(x + off, 12 - hgt - 1, "c")
            x += n
        else:  # ambush
            n = 15
            b.ground(x, x + n)
            for off in (4, 7, 10):
                enemy(x + off, "e")
            if diff >= 2:
                enemy(x + 13, "r")
            maybe_q(x + 7, force=True)
            x += n
    b.ground(x, x + 14)
    b.put(x + 8, 12, "F")
    b.trim(x + 14)
    return b


def lvl_boss():
    b = LB(64)
    b.ground(0, 64)
    b.block(10, 10, 4)
    b.block(24, 10, 5)
    b.block(40, 10, 4)
    b.block(52, 10, 4)
    b.coins(10, 9, 4)
    b.coins(24, 9, 5)
    b.coins(52, 9, 4)
    b.qb(6, 9, "shard")
    b.qb(20, 9, "salve")
    b.qb(34, 9, "salve")
    b.put(46, 12, "B")
    b.put(60, 12, "F")
    return b


LEVELS = [
    dict(name="Линия Света", fn=lvl1, theme=0, stars=1),
    dict(name="Лес Тьмы", fn=lvl2, theme=1, stars=2),
    dict(name="Руины Древних", fn=lambda: gen_level(31, 10, 2), theme=2, stars=2),
    dict(name="Ледяные пики", fn=lambda: gen_level(47, 10, 2), theme=3, stars=3),
    dict(name="Лавовый перевал", fn=lambda: gen_level(59, 12, 3), theme=4, stars=4),
    dict(name="Яма Рошана", fn=lvl_boss, theme=5, stars=5),
]

THEMES = [
    dict(sky=((105, 185, 245), (225, 244, 255)), far=(130, 168, 208), mid=(95, 150, 140), near=(70, 140, 90),
         dirt=(122, 86, 54), grass=(86, 178, 64), amb="fly", stars=False, tint=(255, 240, 200)),
    dict(sky=((60, 30, 78), (240, 128, 86)), far=(112, 60, 100), mid=(84, 46, 80), near=(62, 36, 60),
         dirt=(74, 48, 56), grass=(170, 66, 56), amb="fly", stars=False, tint=(255, 150, 110)),
    dict(sky=((14, 40, 56), (70, 150, 150)), far=(40, 92, 100), mid=(32, 74, 84), near=(26, 58, 68),
         dirt=(66, 78, 82), grass=(110, 190, 170), amb="dust", stars=True, tint=(150, 255, 230)),
    dict(sky=((90, 130, 190), (235, 245, 255)), far=(170, 195, 225), mid=(140, 172, 210), near=(110, 150, 195),
         dirt=(120, 140, 170), grass=(235, 245, 255), amb="snow", stars=False, tint=(210, 235, 255)),
    dict(sky=((36, 8, 10), (230, 90, 30)), far=(96, 30, 28), mid=(74, 24, 24), near=(50, 18, 20),
         dirt=(66, 38, 36), grass=(230, 110, 40), amb="ember", stars=False, tint=(255, 150, 70)),
    dict(sky=((14, 10, 26), (74, 48, 74)), far=(48, 36, 64), mid=(38, 30, 54), near=(30, 24, 42),
         dirt=(64, 54, 66), grass=(120, 96, 132), amb="dust", stars=True, tint=(210, 170, 255)),
]


def make_bg(theme, lvw):
    rnd = random.Random(7 + lvw)
    c0, c1 = theme["sky"]
    sky = HS(SW, SH)
    sky.surf.blit(gradient(c0, c1, 0.9).surf, (0, 0))
    if theme["stars"]:
        for _ in range(110):
            x, y = rnd.randint(0, SW), rnd.randint(0, 300)
            c = rnd.randint(150, 255)
            D.circle(sky, (c, c, c), (x, y), 0.8)
            if rnd.random() < 0.15:
                D.circle(sky, (c, c, 255), (x, y), 1.6)
    layers = []
    spec = ((0.12, 330, theme["far"], 170), (0.28, 395, theme["mid"], 110), (0.5, 450, theme["near"], 70))
    for factor, base, col, amp in spec:
        width = int(SW + (lvw * T - SW) * factor) + 60
        s = HS(width, SH, alpha=True)
        pts = [(0, SH)]
        x = 0
        peaks = []
        while x < width + 90:
            y = base - rnd.randint(0, amp)
            pts.append((x, y))
            peaks.append((x, y))
            x += rnd.randint(55, 140)
        pts.append((width, SH))
        D.polygon(s, col, pts)
        if theme is THEMES[3] and factor < 0.4:
            for px, py in peaks:
                D.polygon(s, (250, 252, 255), [(px, py), (px - 16, py + 26), (px + 16, py + 26)])
        if theme in (THEMES[0], THEMES[1]) and factor >= 0.5:
            for px, py in peaks:
                for k in range(2):
                    tx = px + rnd.randint(-20, 20)
                    D.polygon(s, [max(0, c - 18) for c in col], [(tx, py + 4), (tx - 9, py + 36), (tx + 9, py + 36)])
        layers.append((factor, s))
    return sky, layers


def make_tiles(th):
    rnd = random.Random(5)
    d, g = th["dirt"], th["grass"]

    def shade(c, k):
        return tuple(max(0, min(255, int(v * k))) for v in c)

    def dirt(var):
        s = HSurf((T, T))
        s.fill(d)
        for y in range(0, T, 6):
            D.rect(s, shade(d, 0.97 - 0.12 * y / T), (0, y, T, 6))
        r2 = random.Random(var * 13 + 1)
        for _ in range(5):
            D.circle(s, shade(d, r2.choice((0.82, 1.12))), (r2.randint(4, T - 4), r2.randint(8, T - 4)), r2.randint(2, 4))
        D.line(s, shade(d, 0.7), (0, T - 1), (T, T - 1))
        return s

    tiles = {"dirt": [dirt(0), dirt(1), dirt(2)]}
    gs = dirt(3)
    D.rect(gs, g, (0, 0, T, 9))
    for x in range(0, T, 6):
        D.polygon(gs, g, [(x, 8), (x + 3, 15), (x + 6, 8)])
    D.rect(gs, shade(g, 1.25), (0, 0, T, 3))
    D.line(gs, shade(g, 0.7), (0, 9), (T, 9), 2)
    tiles["grass"] = gs
    br = HSurf((T, T))
    br.fill((150, 150, 170))
    D.rect(br, (196, 196, 214), (0, 0, T, 3))
    D.rect(br, (108, 108, 128), (0, T - 3, T, 3))
    D.rect(br, (96, 96, 116), br.get_rect(), 2)
    D.line(br, (96, 96, 116), (0, T // 2), (T, T // 2), 2)
    D.line(br, (96, 96, 116), (T // 2, 0), (T // 2, T // 2), 2)
    tiles["brick"] = br
    qs = []
    for f in range(4):
        s = HSurf((T, T))
        k = 0.9 + 0.12 * math.sin(f * math.pi / 2)
        s.fill(shade((240, 186, 40), k))
        D.rect(s, shade((255, 235, 140), k), (0, 0, T, 4))
        D.rect(s, shade((170, 110, 20), 1.0), (0, T - 4, T, 4))
        D.rect(s, (130, 80, 14), s.get_rect(), 2)
        for cx, cy in ((4, 4), (T - 5, 4), (4, T - 5), (T - 5, T - 5)):
            D.circle(s, (120, 76, 16), (cx, cy), 2)
        img = F_M.render("?", True, (110, 60, 10))
        s.blit(img, img.get_rect(center=(T // 2 + 1, T // 2 + 2)))
        img = F_M.render("?", True, (255, 250, 220))
        s.blit(img, img.get_rect(center=(T // 2, T // 2)))
        qs.append(s)
    tiles["q"] = qs
    us = HSurf((T, T))
    us.fill((120, 90, 70))
    D.rect(us, (80, 58, 44), us.get_rect(), 2)
    D.rect(us, (140, 108, 86), (2, 2, T - 4, 3))
    tiles["used"] = us
    sp = HSurf((T, T), pygame.SRCALPHA)
    for k in range(3):
        bx = k * (T // 3)
        pts = [(bx, T), (bx + T // 3, T), (bx + T // 6, 12)]
        D.polygon(sp, (196, 202, 214), pts)
        D.polygon(sp, (108, 114, 126), pts, 2)
        D.line(sp, (240, 244, 252), (bx + T // 6, 15), (bx + T // 6 - 2, T - 6), 1)
    tiles["spike"] = sp
    return tiles


DECOR_KINDS = {
    0: ["tree", "tree", "bush", "flower", "flower", "bush"],
    1: ["deadtree", "shroom", "bush", "shroom", "deadtree"],
    2: ["crystal", "crystal", "ruin", "fern", "fern"],
    3: ["pine", "pine", "icicle", "pine"],
    4: ["rock", "vent", "rock", "vent"],
    5: ["bone", "torch", "crystal2", "torch"],
}


def make_decor(w, theme_id):
    """Неосязаемые украшения на земле: деревья, кусты, кристаллы - делают уровни живее."""
    rnd = random.Random(900 + w.idx)
    out = []
    for tx in range(5, w.w - 3):
        for ty in range(ROWS):
            if w.g[ty][tx] == "#":
                free = ty > 0 and all(w.g[ty - 1][x] == " " for x in range(max(0, tx - 1), min(w.w, tx + 2)))
                if free and rnd.random() < 0.2 and not (w.flag and abs(tx - w.flag.centerx // T) < 3):
                    out.append((tx, ty, rnd.choice(DECOR_KINDS[theme_id]), rnd.random() * 6.28, rnd.randint(0, 3)))
                break
    return out


def draw_decor(s, kind, x, y, t, ph, var):
    """x - центр, y - верхняя граница земли."""
    sway = math.sin(t * 0.03 + ph) * 2
    if kind == "tree":
        D.rect(s, (96, 64, 40), (x - 5, y - 44, 10, 46), border_radius=2)
        for cx, cy, r, c in ((0, -58, 21, (54, 134, 66)), (-15, -44, 15, (46, 120, 60)), (15, -44, 15, (46, 120, 60)), (3, -68, 14, (72, 156, 80))):
            D.circle(s, c, (int(x + cx + sway), y + cy), r)
        D.circle(s, (110, 190, 100), (int(x - 6 + sway), y - 66), 7)
    elif kind == "bush":
        D.ellipse(s, (52, 128, 62), (x - 16, y - 16, 32, 20))
        D.ellipse(s, (70, 154, 78), (x - 10, y - 20, 20, 16))
    elif kind == "flower":
        col = ((255, 110, 130), (255, 220, 90), (200, 140, 255), (255, 255, 255))[var]
        D.line(s, (50, 130, 60), (x, y + 2), (x + sway * 0.5, y - 14), 2)
        for k in range(5):
            a = k * 1.256
            D.circle(s, col, (int(x + sway * 0.5 + math.cos(a) * 4), int(y - 15 + math.sin(a) * 4)), 3)
        D.circle(s, (255, 200, 60), (int(x + sway * 0.5), y - 15), 2)
    elif kind == "deadtree":
        c = (44, 30, 42)
        D.line(s, c, (x, y + 2), (x, y - 40), 6)
        D.line(s, c, (x, y - 24), (x - 18 + sway, y - 44), 4)
        D.line(s, c, (x, y - 32), (x + 16 + sway, y - 52), 4)
        D.line(s, c, (x - 12, y - 38), (x - 22, y - 36), 3)
    elif kind == "shroom":
        D.rect(s, (220, 210, 200), (x - 3, y - 14, 6, 16), border_radius=2)
        D.ellipse(s, (150, 70, 170), (x - 12, y - 24, 24, 16))
        D.circle(s, (240, 200, 255), (x - 4, y - 18), 2)
        D.circle(s, (240, 200, 255), (x + 5, y - 16), 2)
        add_glow(s, x, y - 16, 26, (60, 20, 70))
    elif kind in ("crystal", "crystal2"):
        c = (90, 220, 200) if kind == "crystal" else (190, 110, 255)
        g = (20, 70, 64) if kind == "crystal" else (60, 30, 90)
        add_glow(s, x, y - 20, 36, g)
        for dx, hh in ((-8, 26), (0, 40), (9, 22)):
            pts = [(x + dx, y + 2), (x + dx + 6, y + 2 - hh * 0.7), (x + dx + 1, y - hh), (x + dx - 5, y + 2 - hh * 0.7)]
            D.polygon(s, c, pts)
            D.polygon(s, (230, 255, 250), pts, 1)
    elif kind == "ruin":
        D.polygon(s, (120, 140, 146), [(x - 9, y + 2), (x + 9, y + 2), (x + 8, y - 34), (x + 1, y - 40), (x - 3, y - 30), (x - 9, y - 36)])
        D.rect(s, (100, 118, 124), (x - 12, y - 4, 24, 6))
        D.line(s, (80, 96, 100), (x - 2, y - 30), (x + 2, y - 8), 1)
    elif kind == "fern":
        for k in range(5):
            a = -math.pi / 2 + (k - 2) * 0.5
            D.line(s, (60, 170, 150), (x, y + 2), (x + math.cos(a) * 20 + sway, y + math.sin(a) * 20), 3)
    elif kind == "pine":
        D.rect(s, (80, 60, 50), (x - 3, y - 12, 6, 14))
        for k, (w, hh) in enumerate(((30, 22), (24, 20), (18, 18))):
            top = y - 14 - k * 16
            D.polygon(s, (50, 110, 100), [(x - w // 2, top), (x + w // 2, top), (x + sway * 0.4, top - hh)])
            D.polygon(s, (240, 248, 255), [(x - w // 4, top - hh * 0.5), (x + w // 4, top - hh * 0.5), (x + sway * 0.4, top - hh)])
    elif kind == "icicle":
        for dx, hh in ((-7, 18), (0, 30), (8, 16)):
            D.polygon(s, (190, 230, 255), [(x + dx - 4, y + 2), (x + dx + 4, y + 2), (x + dx, y - hh)])
        add_glow(s, x, y - 14, 24, (20, 50, 70))
    elif kind == "rock":
        D.polygon(s, (50, 34, 34), [(x - 16, y + 2), (x - 10, y - 18), (x + 4, y - 24), (x + 16, y - 8), (x + 18, y + 2)])
        D.line(s, (255, 130, 40), (x - 4, y - 18), (x + 2, y - 4), 2)
        add_glow(s, x, y - 8, 28, (60, 24, 6))
    elif kind == "vent":
        D.polygon(s, (60, 38, 36), [(x - 12, y + 2), (x + 12, y + 2), (x + 5, y - 14), (x - 5, y - 14)])
        fl = 6 + math.sin(t * 0.2 + ph) * 3
        D.circle(s, (255, 150, 50), (x, int(y - 16 - fl * 0.5)), int(fl))
        add_glow(s, x, y - 16, 36, (80, 34, 8))
    elif kind == "bone":
        for k in range(4):
            D.arc(s, (226, 220, 200), (x - 14 + k * 4, y - 20, 16, 22), 0.2, 2.9, 3)
        D.line(s, (226, 220, 200), (x - 14, y + 2), (x + 14, y + 2), 3)
    else:  # torch
        D.line(s, (90, 64, 44), (x, y + 2), (x, y - 34), 4)
        fl = 6 + math.sin(t * 0.3 + ph) * 2
        D.circle(s, (255, 170, 60), (x, int(y - 38 - fl * 0.4)), int(fl))
        D.circle(s, (255, 235, 150), (x, int(y - 38 - fl * 0.4)), int(fl * 0.5))
        add_glow(s, x, y - 38, 54, (90, 50, 16))


class Body:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.bump = None

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2


class World:
    def __init__(self, idx):
        self.idx = idx
        info = LEVELS[idx]
        self.name = info["name"]
        self.theme = THEMES[info["theme"]]
        b = info["fn"]()
        self.w = b.w
        self.g = b.g
        self.q = dict(b.q)
        self.px = self.w * T
        self.coins = []
        self.items = []
        self.enemy_spawns = []
        self.flag = None
        self.flag_draw = None
        for ty in range(ROWS):
            for tx in range(self.w):
                ch = self.g[ty][tx]
                if ch == "c":
                    self.coins.append([tx * T + T // 2, ty * T + T // 2, False])
                elif ch == "+":
                    self.items.append([tx * T + T // 2, ty * T + T // 2, False])
                elif ch in "erB":
                    self.enemy_spawns.append((ch, tx, ty))
                elif ch == "F":
                    self.flag = pygame.Rect(tx * T - 6, 0, T + 12, (ty + 1) * T)
                    self.flag_draw = pygame.Rect(tx * T, (ty - 4) * T, T, 5 * T)
                if ch in "cerB+F":
                    self.g[ty][tx] = " "
        self.flag_needs_boss = any(s[0] == "B" for s in self.enemy_spawns)
        self.build_gfx()
        self.decor = make_decor(self, info["theme"])

    def build_gfx(self):
        """Фон и тайлы зависят от разрешения рендера, поэтому пересоздаются при смене качества."""
        self.sky, self.layers = make_bg(self.theme, self.w)
        self.tiles = make_tiles(self.theme)

    def solid(self, tx, ty):
        if tx < 0 or tx >= self.w:
            return True
        if ty < 0 or ty >= ROWS:
            return False
        return self.g[ty][tx] in "#=?%"

    def tile(self, tx, ty):
        if 0 <= tx < self.w and 0 <= ty < ROWS:
            return self.g[ty][tx]
        return " "

    def move(self, b, dx, dy):
        hit_x = False
        b.bump = None
        b.x += dx
        if dx:
            x0, x1 = int(b.x // T), int((b.x + b.w - 0.01) // T)
            y0, y1 = int(b.y // T), int((b.y + b.h - 0.01) // T)
            for ty in range(y0, y1 + 1):
                for tx in range(x0, x1 + 1):
                    if self.solid(tx, ty):
                        b.x = tx * T - b.w if dx > 0 else (tx + 1) * T
                        hit_x = True
        b.y += dy
        b.on_ground = False
        if dy:
            x0, x1 = int(b.x // T), int((b.x + b.w - 0.01) // T)
            y0, y1 = int(b.y // T), int((b.y + b.h - 0.01) // T)
            best = None
            for ty in range(y0, y1 + 1):
                for tx in range(x0, x1 + 1):
                    if self.solid(tx, ty):
                        if dy > 0:
                            b.y = ty * T - b.h
                            b.on_ground = True
                        else:
                            b.y = (ty + 1) * T
                            d = abs(tx * T + T / 2 - (b.x + b.w / 2))
                            if best is None or d < best[0]:
                                best = (d, tx, ty)
                        b.vy = 0
            if best is not None and dy < 0:
                b.bump = (best[1], best[2])
        return hit_x


# --------------------------------------------------------------- герои ------
HEROES = [
    dict(id="pudge", name="PUDGE", title="Мясник", w=40, h=54, speed=3.0, jump=12.6, hp=6,
         ab=[("Meat Hook", "J", 70), ("Rot", "K", 330)],
         info=["Здоровье: 6", "Скорость: медленно", "Прыжок: средний"],
         ab_info=["J  Meat Hook: крюк тянет врага", "K  Rot: ядовитое облако"]),
    dict(id="invoker", name="INVOKER", title="Заклинатель", w=28, h=56, speed=3.8, jump=13.0, hp=4,
         ab=[("Chaos Meteor", "J", 55), ("Ghost Walk", "K", 420)],
         info=["Здоровье: 4", "Скорость: средне", "Прыжок: хороший"],
         ab_info=["J  Chaos Meteor: метеорит", "K  Ghost Walk: неуязвимость"]),
    dict(id="meepo", name="MEEPO", title="Копатель", w=24, h=34, speed=4.8, jump=13.4, hp=4,
         ab=[("Poof", "J", 50), ("Earthbind", "K", 110)],
         info=["Здоровье: 4", "Скорость: быстро", "Двойной прыжок"],
         ab_info=["J  Poof: рывок вперёд", "K  Earthbind: сеть замораживает"]),
    dict(id="shaker", name="EARTHSHAKER", title="Громила", w=40, h=56, speed=3.3, jump=12.8, hp=5,
         ab=[("Echo Slam", "J", 150), ("Enchant Totem", "K", 360)],
         info=["Здоровье: 5", "Скорость: средне", "Прыжок: средний"],
         ab_info=["J  Echo Slam: удар по земле", "K  Totem: супер-прыжок и удар"]),
]

SHARD_TEXT = {
    "pudge": "Шард: крюк длиннее и бьёт сильнее, облако шире",
    "invoker": "Шард: два метеорита, призрак дольше",
    "meepo": "Шард: рывок длиннее, сеть шире и дольше",
    "shaker": "Шард: удар шире и оглушает, тотем дольше",
}


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def blob(s, cx, cy, rx, ry, col, rim=0.58, hi=1.3):
    """Объёмный овал: тёмный край, основной цвет и блик."""
    D.ellipse(s, shade(col, rim), (cx - rx, cy - ry, rx * 2, ry * 2))
    D.ellipse(s, col, (cx - rx, cy - ry, rx * 1.8, ry * 1.82))
    D.ellipse(s, shade(col, hi), (cx - rx * 0.7, cy - ry * 0.8, rx * 0.8, ry * 0.52))


def limb(s, p0, p1, w, col, rim=0.58):
    """Округлая конечность с тёмным краем."""
    D.line(s, shade(col, rim), p0, p1, w + 1.8)
    D.circle(s, shade(col, rim), p0, (w + 1.8) / 2)
    D.circle(s, shade(col, rim), p1, (w + 1.8) / 2)
    D.line(s, col, p0, p1, w)
    D.circle(s, col, p0, w / 2)
    D.circle(s, col, p1, w / 2)


def draw_pudge(s, ox, oy, a, moving, air, t, pw):
    sw = math.sin(a) * 5 if moving and not air else (4 if air else 0)
    bob = abs(math.sin(a)) * 1.5 if moving and not air else 0
    skin = (136, 162, 104)
    # цепь с крюком у пояса
    for k in range(7):
        D.circle(s, (176, 178, 186), (ox - 19 - k * 0.8, oy - 25 + k * 2.3 + math.sin(t * 0.1 + k) * 0.5), 1.6, 1)
    D.arc(s, (206, 208, 214), (ox - 27, oy - 10, 12, 12), 3.3, 6.1, 2.4)
    D.polygon(s, (206, 208, 214), [(ox - 15.5, oy - 5), (ox - 13, oy - 8), (ox - 12.5, oy - 4)])
    # ноги и сапоги
    for dx, ph in ((-9, sw), (8, -sw)):
        D.rect(s, (60, 64, 58), (ox + dx - 6 + ph, oy - 15, 12, 15), border_radius=4)
        D.rect(s, (34, 30, 32), (ox + dx - 8 + ph, oy - 7, 16, 7), border_radius=3)
        D.rect(s, (84, 78, 76), (ox + dx - 7 + ph, oy - 7, 14, 1.8), border_radius=1)
    # задняя рука
    limb(s, (ox - 15, oy - 36 - bob), (ox - 20, oy - 23 - bob + sw * 0.2), 6.5, shade(skin, 0.88))
    # туловище
    blob(s, ox, oy - 28 - bob, 23, 18.5, skin)
    D.line(s, (98, 62, 60), (ox - 15, oy - 37 - bob), (ox + 12, oy - 25 - bob), 1.8)
    for k in range(6):
        px, py = ox - 13 + k * 4.5, oy - 36.5 + k * 2.15 - bob
        D.line(s, (58, 38, 38), (px - 1.2, py - 2.4), (px + 1.2, py + 2.4), 1.1)
    # кровавый фартук
    ap = [(ox - 16, oy - 27 - bob), (ox + 16, oy - 27 - bob), (ox + 18, oy - 12 - bob), (ox + 12, oy - 9 - bob),
          (ox + 6, oy - 12 - bob), (ox, oy - 8 - bob), (ox - 7, oy - 12 - bob), (ox - 12, oy - 9 - bob), (ox - 18, oy - 12 - bob)]
    D.polygon(s, (222, 216, 198), ap)
    D.polygon(s, (186, 180, 162), [(ox - 16, oy - 27 - bob), (ox - 7, oy - 27 - bob), (ox - 11, oy - 12 - bob), (ox - 18, oy - 12 - bob)])
    for px, py, r in ((-6, -22, 3), (6, -19, 2.4), (-1, -15, 2), (10, -24, 1.8), (-11, -17, 1.6)):
        D.circle(s, (150, 22, 24), (ox + px, oy + py - bob), r)
    D.line(s, (150, 22, 24), (ox + 6, oy - 19 - bob), (ox + 6, oy - 13 - bob), 1.2)
    D.polygon(s, (214, 208, 190), ap, 1)
    D.rect(s, (70, 52, 40), (ox - 18, oy - 29 - bob, 36, 3.4), border_radius=1)
    D.rect(s, (200, 170, 70), (ox - 2, oy - 29.6 - bob, 4, 4.4), border_radius=1)
    D.line(s, (80, 60, 46), (ox - 12, oy - 28 - bob), (ox - 5, oy - 41 - bob), 3)
    D.line(s, (80, 60, 46), (ox + 12, oy - 28 - bob), (ox + 8, oy - 41 - bob), 3)
    # голова
    blob(s, ox + 6, oy - 49 - bob, 10.5, 9.5, (150, 176, 118))
    D.polygon(s, (36, 32, 34), [(ox - 3, oy - 53 - bob), (ox, oy - 64 - bob), (ox + 3, oy - 56 - bob), (ox + 6, oy - 66 - bob),
                                (ox + 9, oy - 57 - bob), (ox + 13, oy - 63 - bob), (ox + 14, oy - 53 - bob)])
    D.line(s, (46, 38, 32), (ox + 5, oy - 52.5 - bob), (ox + 15, oy - 50.5 - bob), 2.2)
    D.circle(s, (255, 226, 70), (ox + 11, oy - 48.6 - bob), 2.4)
    D.circle(s, (50, 24, 10), (ox + 11.7, oy - 48.6 - bob), 1.1)
    D.polygon(s, (44, 30, 30), [(ox + 5, oy - 44 - bob), (ox + 16, oy - 44.5 - bob), (ox + 15, oy - 40.5 - bob), (ox + 6, oy - 40.5 - bob)])
    for k in range(3):
        D.polygon(s, (240, 236, 220), [(ox + 7 + k * 3, oy - 44 - bob), (ox + 9 + k * 3, oy - 44 - bob), (ox + 8 + k * 3, oy - 41 - bob)])
    # передняя рука и тесак
    swing = math.sin(t * 0.3) * 4 if pw else 0
    hand = (ox + 27, oy - 32 - bob + swing)
    limb(s, (ox + 15, oy - 38 - bob), hand, 7, skin)
    D.line(s, (110, 70, 36), (hand[0] - 1, hand[1] + 4), (hand[0] + 3, hand[1] - 11), 3.4)
    D.line(s, (60, 40, 22), (hand[0], hand[1] + 1), (hand[0] + 1.6, hand[1] - 3), 3.6)
    bx, by = hand[0] + 2, hand[1] - 11
    blade = [(bx - 1, by), (bx + 13, by - 5), (bx + 14.5, by + 12), (bx + 2, by + 13)]
    D.polygon(s, (196, 202, 210), blade)
    D.polygon(s, (240, 244, 248), [(bx - 1, by), (bx + 13, by - 5), (bx + 13.4, by - 1.5), (bx - 0.4, by + 3)])
    D.polygon(s, (110, 116, 126), blade, 1.2)
    D.circle(s, (150, 22, 24), (bx + 9, by + 6), 1.8)
    D.line(s, (150, 22, 24), (bx + 4, by + 8), (bx + 6, by + 12), 1.4)


def draw_invoker(s, ox, oy, a, moving, air, t, pw):
    sw = math.sin(a) * 3 if moving and not air else 0
    bob = abs(math.sin(a)) * 1.2 if moving and not air else 0
    gold, white = (226, 180, 62), (244, 240, 228)
    flut = math.sin(t * 0.12) * 2 + (4 if moving else 0)
    # плащ
    D.polygon(s, (176, 52, 66), [(ox - 8, oy - 41 - bob), (ox + 3, oy - 41 - bob), (ox - 15 - flut, oy - 5), (ox - 3, oy - 3)])
    D.polygon(s, (214, 96, 90), [(ox - 8, oy - 41 - bob), (ox - 3, oy - 41 - bob), (ox - 11 - flut, oy - 6), (ox - 15 - flut, oy - 5)])
    # сапоги
    for dx, ph in ((-8, sw), (1, -sw)):
        D.rect(s, (98, 66, 44), (ox + dx + ph, oy - 7, 8, 7), border_radius=2)
        D.rect(s, gold, (ox + dx + ph, oy - 7, 8, 1.6))
    # роба
    D.polygon(s, shade(white, 0.8), [(ox - 14, oy - 3), (ox + 14, oy - 3), (ox + 9, oy - 40 - bob), (ox - 9, oy - 40 - bob)])
    D.polygon(s, white, [(ox - 12, oy - 3), (ox + 11, oy - 3), (ox + 8, oy - 40 - bob), (ox - 8, oy - 40 - bob)])
    D.polygon(s, gold, [(ox - 14, oy - 3), (ox + 14, oy - 3), (ox + 13.2, oy - 8.5), (ox - 13.2, oy - 8.5)])
    for k in range(5):
        D.polygon(s, (170, 40, 56), [(ox - 10 + k * 5, oy - 5.8), (ox - 8 + k * 5, oy - 4.4), (ox - 10 + k * 5, oy - 3.2), (ox - 12 + k * 5, oy - 4.4)])
    D.polygon(s, (126, 52, 150), [(ox - 3.5, oy - 40 - bob), (ox + 3.5, oy - 40 - bob), (ox + 5.5, oy - 9), (ox - 5.5, oy - 9)])
    D.line(s, gold, (ox, oy - 38 - bob), (ox, oy - 10), 1.2)
    D.line(s, gold, (ox - 3.5, oy - 40 - bob), (ox - 5.5, oy - 9), 1)
    D.line(s, gold, (ox + 3.5, oy - 40 - bob), (ox + 5.5, oy - 9), 1)
    # высокий воротник сзади
    D.polygon(s, shade(white, 0.86), [(ox - 12, oy - 38 - bob), (ox + 9, oy - 38 - bob), (ox + 13, oy - 60 - bob), (ox - 13, oy - 60 - bob)])
    D.polygon(s, gold, [(ox - 13, oy - 60 - bob), (ox + 13, oy - 60 - bob), (ox + 13, oy - 57.4 - bob), (ox - 13, oy - 57.4 - bob)])
    # плечи
    D.polygon(s, white, [(ox - 14, oy - 35 - bob), (ox + 14, oy - 35 - bob), (ox + 10, oy - 42 - bob), (ox - 10, oy - 42 - bob)])
    D.polygon(s, gold, [(ox - 14, oy - 35 - bob), (ox + 14, oy - 35 - bob), (ox + 13, oy - 37 - bob), (ox - 13, oy - 37 - bob)])
    # длинные белые волосы
    D.polygon(s, (240, 240, 250), [(ox - 11, oy - 58 - bob), (ox + 10, oy - 58 - bob), (ox + 12, oy - 36 - bob), (ox - 12, oy - 36 - bob)])
    D.polygon(s, (214, 216, 232), [(ox - 11, oy - 58 - bob), (ox - 6, oy - 58 - bob), (ox - 8, oy - 36 - bob), (ox - 12, oy - 36 - bob)])
    # лицо
    blob(s, ox + 1.5, oy - 49 - bob, 8, 8.8, (234, 194, 160), rim=0.7)
    D.polygon(s, (246, 246, 252), [(ox - 8, oy - 52 - bob), (ox + 11, oy - 52 - bob), (ox + 9, oy - 60 - bob), (ox - 6, oy - 60 - bob)])
    D.line(s, gold, (ox - 6.5, oy - 53 - bob), (ox + 10, oy - 53 - bob), 1.8)
    D.circle(s, (255, 140, 40), (ox + 6, oy - 49.5 - bob), 1.8)
    D.circle(s, (255, 230, 150), (ox + 6.4, oy - 49.8 - bob), 0.8)
    D.line(s, (150, 96, 70), (ox + 3, oy - 44 - bob), (ox + 7, oy - 44.2 - bob), 1)
    # рука с сферой
    lift = math.sin(t * 0.3) * 3 if pw else 0
    hand = (ox + 14, oy - 30 - bob + lift)
    limb(s, (ox + 8, oy - 36 - bob), hand, 4.6, (234, 194, 160), rim=0.7)
    D.polygon(s, white, [(ox + 5, oy - 38 - bob), (ox + 12, oy - 36 - bob), (ox + 16, oy - 30 - bob + lift), (ox + 9, oy - 32 - bob + lift)])
    D.circle(s, (255, 190, 70, 120), (hand[0] + 4, hand[1] - 3), 6)
    D.circle(s, (255, 210, 120), (hand[0] + 4, hand[1] - 3), 3.2)
    # три сферы вокруг головы (Quas / Wex / Exort)
    cols = ((90, 180, 255), (206, 100, 255), (255, 150, 46))
    for k, c in enumerate(cols):
        ang = t * 0.07 + k * 2.094
        cx, cy = ox + math.cos(ang) * 19, oy - 64 - bob + math.sin(ang) * 5
        D.circle(s, (*c, 90), (cx, cy), 7.2)
        D.circle(s, c, (cx, cy), 4.6)
        D.circle(s, (255, 255, 255), (cx - 1.4, cy - 1.4), 1.8)


def draw_meepo(s, ox, oy, a, moving, air, t, pw):
    sw = math.sin(a * 1.4) * 4 if moving and not air else (3 if air else 0)
    bob = abs(math.sin(a * 1.4)) * 1.2 if moving and not air else 0
    fur, belly = (206, 160, 104), (240, 214, 170)
    # хвост
    blob(s, ox - 12, oy - 13 - bob, 5.5, 8, shade(fur, 0.92))
    # ноги
    for dx, ph in ((-7, sw), (3, -sw)):
        D.rect(s, (112, 76, 48), (ox + dx + ph, oy - 8, 7, 8), border_radius=3)
        D.rect(s, (78, 52, 34), (ox + dx - 1 + ph, oy - 3, 9, 3), border_radius=2)
    # тело
    blob(s, ox, oy - 14 - bob, 11.5, 10, fur)
    D.ellipse(s, belly, (ox - 5, oy - 17 - bob, 11, 9))
    # голубой шарф
    flut = math.sin(t * 0.15) * 1.5 + (3 if moving else 0)
    D.polygon(s, (40, 82, 160), [(ox - 11, oy - 21 - bob), (ox + 11, oy - 21 - bob), (ox + 9, oy - 16.5 - bob), (ox - 9, oy - 16.5 - bob)])
    D.polygon(s, (66, 120, 214), [(ox - 11, oy - 21 - bob), (ox + 11, oy - 21 - bob), (ox + 10.5, oy - 19 - bob), (ox - 10.5, oy - 19 - bob)])
    D.polygon(s, (50, 98, 188), [(ox - 8, oy - 18 - bob), (ox - 3, oy - 17 - bob), (ox - 12 - flut, oy - 8), (ox - 16 - flut, oy - 11)])
    # большие уши
    D.polygon(s, fur, [(ox - 7, oy - 33 - bob), (ox - 14, oy - 48 - bob), (ox - 1, oy - 37 - bob)])
    D.polygon(s, (246, 176, 170), [(ox - 7.6, oy - 35 - bob), (ox - 12, oy - 45 - bob), (ox - 3, oy - 37.4 - bob)])
    D.polygon(s, fur, [(ox + 4, oy - 38 - bob), (ox + 13, oy - 49 - bob), (ox + 12, oy - 31 - bob)])
    D.polygon(s, (246, 176, 170), [(ox + 6, oy - 37 - bob), (ox + 11, oy - 45 - bob), (ox + 10.4, oy - 33 - bob)])
    # голова
    blob(s, ox + 2, oy - 30 - bob, 10.5, 9.8, fur)
    D.ellipse(s, belly, (ox + 3, oy - 27 - bob, 9, 6.5))
    D.circle(s, (255, 255, 255), (ox + 6, oy - 31 - bob), 3.6)
    D.circle(s, (24, 20, 34), (ox + 6.9, oy - 31 - bob), 2.3)
    D.circle(s, (255, 255, 255), (ox + 7.6, oy - 32 - bob), 0.9)
    D.circle(s, (70, 44, 40), (ox + 12.4, oy - 27 - bob), 2.3)
    D.line(s, (110, 70, 54), (ox + 8, oy - 24.4 - bob), (ox + 11.5, oy - 24.6 - bob), 1)
    # налобный фонарь
    D.rect(s, (80, 60, 44), (ox - 3, oy - 38.4 - bob, 11, 2.2), border_radius=1)
    D.circle(s, (255, 235, 120, 130), (ox + 5, oy - 38.4 - bob), 4.2)
    D.circle(s, (255, 240, 160), (ox + 5, oy - 38.4 - bob), 2.4)
    # кирка
    sw2 = math.sin(t * 0.3) * 5 if pw else 0
    hand = (ox + 14, oy - 22 - bob + sw2)
    limb(s, (ox + 7, oy - 15 - bob), hand, 4, shade(fur, 0.95))
    D.line(s, (110, 72, 40), (hand[0] - 2, hand[1] + 6), (hand[0] + 4, hand[1] - 12), 2.8)
    D.polygon(s, (186, 192, 204), [(hand[0] - 1, hand[1] - 15), (hand[0] + 12, hand[1] - 12), (hand[0] + 4, hand[1] - 9), (hand[0] - 5, hand[1] - 11)])
    D.polygon(s, (240, 244, 250), [(hand[0] - 1, hand[1] - 15), (hand[0] + 12, hand[1] - 12), (hand[0] + 9, hand[1] - 12.4), (hand[0] - 2, hand[1] - 13.6)])


def draw_shaker(s, ox, oy, a, moving, air, t, pw, totem=False):
    sw = math.sin(a) * 4 if moving and not air else (3 if air else 0)
    bob = abs(math.sin(a)) * 1.3 if moving and not air else 0
    brown, stone = (122, 82, 54), (152, 154, 168)
    glow = (255, 160, 50) if totem else (84, 206, 255)
    # ноги и копыта
    for dx, ph in ((-10, sw), (3, -sw)):
        D.rect(s, (84, 56, 38), (ox + dx + ph, oy - 15, 12, 15), border_radius=3)
        D.rect(s, (40, 32, 32), (ox + dx - 1 + ph, oy - 6, 14, 6), border_radius=2)
    # задняя рука
    limb(s, (ox - 17, oy - 38 - bob), (ox - 20, oy - 24 - bob), 8, shade(brown, 0.9))
    # торс
    blob(s, ox, oy - 29 - bob, 19, 16, brown)
    D.ellipse(s, shade(brown, 1.2), (ox - 9, oy - 34 - bob, 18, 14))
    D.line(s, glow, (ox - 6, oy - 36 - bob), (ox + 6, oy - 36 - bob), 1.6)
    D.line(s, glow, (ox - 8, oy - 30 - bob), (ox + 8, oy - 30 - bob), 1.6)
    D.line(s, glow, (ox, oy - 38 - bob), (ox, oy - 24 - bob), 1.6)
    D.rect(s, (66, 46, 34), (ox - 19, oy - 17 - bob, 38, 4), border_radius=1)
    # каменные наплечники
    for sx in (-1, 1):
        px, py = ox + sx * 19, oy - 39 - bob
        blob(s, px, py, 9.5, 8.5, stone, rim=0.55, hi=1.2)
        D.line(s, (80, 82, 96), (px - 3, py - 6), (px + 1, py + 2), 1.1)
        D.line(s, glow, (px + 2, py - 3), (px + 4, py + 3), 1.4)
    # голова быка
    blob(s, ox + 2, oy - 50 - bob, 10, 9.6, (160, 116, 84))
    D.ellipse(s, (194, 152, 118), (ox + 4, oy - 49 - bob, 12, 8.4))
    D.circle(s, (70, 44, 36), (ox + 12.6, oy - 46 - bob), 1.1)
    D.circle(s, (226, 188, 70), (ox + 15, oy - 44.4 - bob), 2.2, 1)
    D.circle(s, glow, (ox + 7, oy - 52 - bob), 2.4)
    D.circle(s, (255, 255, 255), (ox + 7.4, oy - 52.4 - bob), 0.9)
    D.line(s, (60, 40, 30), (ox + 3, oy - 55.4 - bob), (ox + 11, oy - 53.6 - bob), 1.8)
    D.polygon(s, (60, 44, 34), [(ox - 8, oy - 43 - bob), (ox + 6, oy - 43 - bob), (ox + 2, oy - 36 - bob), (ox - 4, oy - 36 - bob)])
    # рога
    for hx, sg in ((ox - 7, -1), (ox + 11, 1)):
        hy = oy - 54 - bob
        horn = [(hx, hy + 2), (hx + sg * 9, hy + 1), (hx + sg * 14, hy - 6), (hx + sg * 13, hy - 15), (hx + sg * 9, hy - 8),
                (hx + sg * 4, hy - 4), (hx - sg * 1, hy - 4)]
        D.polygon(s, (242, 236, 212), horn)
        D.polygon(s, (186, 176, 150), [(hx, hy + 2), (hx + sg * 9, hy + 1), (hx + sg * 14, hy - 6), (hx + sg * 11, hy - 5), (hx + sg * 7, hy - 1), (hx, hy - 1)])
        D.polygon(s, (110, 100, 84), horn, 1)
    # передняя рука и тотем
    lift = math.sin(t * 0.3) * 4 if pw else 0
    hand = (ox + 25, oy - 30 - bob + lift)
    limb(s, (ox + 18, oy - 37 - bob), hand, 8, brown)
    D.line(s, (96, 62, 36), (hand[0], oy - 4 + lift), (hand[0], oy - 66 - bob + lift), 6.5)
    D.line(s, (140, 96, 58), (hand[0] - 1.4, oy - 6 + lift), (hand[0] - 1.4, oy - 64 - bob + lift), 1.6)
    for k in range(3):
        D.rect(s, (66, 44, 28), (hand[0] - 5, oy - 30 - k * 12 - bob + lift, 10, 2.2), border_radius=1)
        D.circle(s, glow, (hand[0], oy - 25 - k * 12 - bob + lift), 2.4)
    D.circle(s, (255, 190, 80) if totem else (140, 226, 255), (hand[0], oy - 69 - bob + lift), 4.6)
    D.circle(s, (255, 255, 255), (hand[0] - 1, oy - 70 - bob + lift), 1.4)


DRAWERS = {"pudge": draw_pudge, "invoker": draw_invoker, "meepo": draw_meepo}


_hero_cache = {}
_cache_clearers.append(_hero_cache.clear)


def hero_surface(hid, a, moving, air, t, pw, totem=False, outline=True, zoom=1.0):
    """Спрайт героя. zoom рисует его крупнее сразу в высоком разрешении (без размытия).
    Неподвижные герои (меню, карта) кэшируются: анимируются только шары Invoker."""
    idle = not moving and not air and not pw and not totem and outline
    if idle:
        key = (hid, round(zoom, 2), K, int(t // 3) % 32 if hid == "invoker" else 0)
        hit = _hero_cache.get(key)
        if hit is not None:
            return hit
        spr = _hero_surface(hid, a, moving, air, t, pw, totem, outline, zoom)
        if len(_hero_cache) > 120:
            _hero_cache.clear()
        _hero_cache[key] = spr
        return spr
    return _hero_surface(hid, a, moving, air, t, pw, totem, outline, zoom)


def _hero_surface(hid, a, moving, air, t, pw, totem=False, outline=True, zoom=1.0):
    global K
    k0 = K
    K = k0 * zoom
    try:
        s = HS(110, 120, alpha=True)
        if hid == "shaker":
            draw_shaker(s, 50, 112, a, moving, air, t, pw, totem)
        else:
            DRAWERS[hid](s, 50, 112, a, moving, air, t, pw)
        if outline:
            sil = pygame.mask.from_surface(s.surf, 60).to_surface(setcolor=(16, 14, 30, 255), unsetcolor=(0, 0, 0, 0))
            out = HS(110, 120, alpha=True)
            r = max(1, int(round(1.5 * K)))
            for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r), (-r, -r), (r, r), (-r, r), (r, -r)):
                out.surf.blit(sil, (dx, dy))
            out.surf.blit(s.surf, (0, 0))
            s = out
    finally:
        K = k0
    s.lw, s.lh = 110 * zoom, 120 * zoom
    return s



def draw_crystal(s, x, y, size, t, col=(110, 220, 255)):
    pts = [(x, y - size), (x + size * 0.6, y), (x, y + size), (x - size * 0.6, y)]
    D.polygon(s, col, pts)
    D.polygon(s, (230, 250, 255), pts, 2)
    D.polygon(s, (255, 255, 255), [(x, y - size), (x + size * 0.25, y - size * 0.2), (x - size * 0.25, y - size * 0.2)])


class Player(Body):
    def __init__(self, hero_idx, x, y, prog):
        h = HEROES[hero_idx]
        super().__init__(x, y - h["h"], h["w"], h["h"])
        self.hero = h
        self.hid = h["id"]
        up = prog["up"]
        self.maxhp = h["hp"] + up.get("vit", 0)
        self.hp = self.maxhp
        self.speed = h["speed"] * (1 + 0.08 * up.get("boots", 0))
        self.jump = h["jump"]
        self.cdmul = 0.8 ** up.get("cd", 0)
        self.shard = bool(prog.get("shard"))
        self.facing = 1
        self.was_ground = False
        self.cd = [0, 0]
        self.cdmax = [1, 1]
        self.inv = 0
        self.ghost = 0
        self.rot = 0
        self.rot_r = 95
        self.totem = 0
        self.totem_jump = False
        self.air_jumps = 1
        self.coyote = 0
        self.jbuf = 0
        self.anim = 0.0
        self.pb = self.y + self.h
        self.cast_t = 0
        self.sq = 1.0
        self.safe = (self.x, self.y)

    @property
    def cd_scale(self):
        return self.cdmul * (0.7 if self.shard else 1.0)


class Enemy(Body):
    def __init__(self, kind, tx, ty):
        dims = {"e": (30, 32, 1), "r": (30, 38, 2), "B": (96, 84, 14)}
        w, h, hp = dims[kind]
        super().__init__(tx * T + (T - w) / 2, (ty + 1) * T - h, w, h)
        self.kind = kind
        self.hp = self.maxhp = hp
        self.dir = -1
        self.alive = True
        self.frozen = 0
        self.stun = 0
        self.flash = 0
        self.inv = 0
        self.cd = random.randint(30, 90)
        self.t = random.randint(0, 100)
        self.awake = kind != "B"
        self.jumping = False
        self.jump_cd = 120


# ----------------------------------------------------------------- враги ----
def draw_creep(s, r, e, t):
    col = (176, 62, 52)
    d = e.dir
    ph = math.sin(e.t * 0.2) * 3 if e.frozen == 0 and e.stun == 0 else 0
    x, y = r.x, r.y
    D.rect(s, (70, 40, 40), (x + 5 + ph, y + 24, 8, 8), border_radius=2)
    D.rect(s, (70, 40, 40), (x + 17 - ph, y + 24, 8, 8), border_radius=2)
    D.rect(s, col, (x + 3, y + 10, 24, 18), border_radius=5)
    D.rect(s, (214, 96, 84), (x + 5, y + 12, 20, 4), border_radius=2)
    D.circle(s, (200, 150, 120), (x + 15, y + 9), 8)
    D.polygon(s, (110, 110, 120), [(x + 6, y + 8), (x + 15, y - 2), (x + 24, y + 8)])
    D.circle(s, (255, 240, 120), (x + 15 + d * 3, y + 9), 2)
    cx = x + 15 + d * 15
    D.line(s, (100, 65, 35), (cx, y + 28), (cx + d * 2, y + 8), 4)
    D.circle(s, (120, 80, 45), (cx + d * 2, y + 7), 5)
    if e.flash:
        D.rect(s, (255, 255, 255), r, 2, border_radius=4)
    if e.frozen:
        D.rect(s, (150, 220, 255), r.inflate(6, 6), 3, border_radius=6)


def draw_ranged(s, r, e, t, px):
    d = 1 if px > e.cx else -1
    x, y = r.x, r.y
    D.rect(s, (60, 40, 70), (x + 6, y + 30, 8, 8), border_radius=2)
    D.rect(s, (60, 40, 70), (x + 16, y + 30, 8, 8), border_radius=2)
    D.polygon(s, (120, 70, 150), [(x + 3, y + 32), (x + 27, y + 32), (x + 22, y + 12), (x + 8, y + 12)])
    D.circle(s, (200, 150, 120), (x + 15, y + 10), 8)
    D.polygon(s, (90, 50, 120), [(x + 5, y + 8), (x + 15, y - 6), (x + 25, y + 8)])
    D.circle(s, (255, 240, 120), (x + 15 + d * 3, y + 10), 2)
    D.line(s, (100, 65, 35), (x + 15 + d * 14, y + 36), (x + 15 + d * 14, y + 4), 3)
    D.circle(s, (180, 90, 255), (x + 15 + d * 14, y + 3), 5)
    add_glow(s, x + 15 + d * 14, y + 3, 16, (90, 40, 130))
    if e.flash:
        D.rect(s, (255, 255, 255), r, 2, border_radius=4)
    if e.frozen:
        D.rect(s, (150, 220, 255), r.inflate(6, 6), 3, border_radius=6)


def draw_boss(s, r, e, t, enraged):
    x, y, w, h = r.x, r.y, r.w, r.h
    d = e.dir
    body = (112, 92, 80) if not enraged else (140, 80, 70)
    ph = math.sin(e.t * 0.12) * 4 if e.on_ground else 0
    D.rect(s, (70, 56, 50), (x + 12 + ph, y + h - 22, 24, 22), border_radius=4)
    D.rect(s, (70, 56, 50), (x + w - 36 - ph, y + h - 22, 24, 22), border_radius=4)
    D.ellipse(s, body, (x, y + 18, w, h - 28))
    D.ellipse(s, (80, 64, 56), (x, y + 18, w, h - 28), 3)
    D.ellipse(s, (200, 180, 150), (x + 20, y + 40, w - 40, 30))
    hx = x + w // 2 + d * 18
    D.circle(s, body, (hx, y + 22), 22)
    D.circle(s, (80, 64, 56), (hx, y + 22), 22, 3)
    for sgn in (-1, 1):
        D.polygon(s, (230, 220, 190), [(hx + sgn * 14, y + 8), (hx + sgn * 28, y - 12), (hx + sgn * 20, y + 14)])
    eye = (255, 70, 30) if enraged else (255, 190, 40)
    D.circle(s, eye, (hx + d * 8, y + 18), 4)
    D.circle(s, eye, (hx - d * 4, y + 18), 4)
    add_glow(s, hx + d * 2, y + 18, 26, (110, 40, 10) if enraged else (90, 70, 10))
    D.rect(s, (40, 25, 25), (hx - 10 + d * 6, y + 30, 20, 7))
    for k in range(4):
        D.polygon(s, (240, 235, 215), [(hx - 9 + d * 6 + k * 5, y + 30), (hx - 6 + d * 6 + k * 5, y + 30), (hx - 8 + d * 6 + k * 5, y + 36)])
    if e.flash and (e.flash // 3) % 2 == 0:
        D.ellipse(s, (255, 255, 255), (x, y + 18, w, h - 28), 3)
    if e.frozen:
        D.rect(s, (150, 220, 255), r.inflate(8, 8), 4, border_radius=10)


def draw_star(s, x, y, r, filled=True):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((x + math.cos(ang) * rr, y + math.sin(ang) * rr))
    if filled:
        D.polygon(s, (255, 214, 70), pts)
        D.polygon(s, (190, 130, 20), pts, 1)
    else:
        D.polygon(s, (110, 110, 130), pts, 1)


def draw_heart(s, x, y, full):
    col = (232, 56, 76) if full else (62, 40, 52)
    D.circle(s, col, (x + 6, y + 6), 6)
    D.circle(s, col, (x + 16, y + 6), 6)
    D.polygon(s, col, [(x, y + 8), (x + 22, y + 8), (x + 11, y + 22)])
    if full:
        D.circle(s, (255, 170, 180), (x + 5, y + 4), 2)


# ------------------------------------------------------------ карта мира ----
MAP_NODES = {1: (120, 410), 2: (270, 335), 3: (440, 210), 4: (450, 400), 5: (640, 320), 6: (820, 185)}
MAP_CTRL = {(1, 2): (170, 345), (2, 3): (330, 225), (2, 4): (340, 410), (3, 5): (580, 220),
            (4, 5): (570, 410), (5, 6): (760, 320)}
MAP_EDGES = list(MAP_CTRL.keys())
SHOP_POS = (150, 190)


def edge_point(a, b, t):
    key = (min(a, b), max(a, b))
    if a > b:
        t = 1 - t
    p0, p1, c = MAP_NODES[key[0]], MAP_NODES[key[1]], MAP_CTRL[key]
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1])


def neighbors(n):
    return [b if a == n else a for a, b in MAP_EDGES if n in (a, b)]


def make_map_surface():
    rnd = random.Random(11)
    s = HSurf((SW, SH))
    for y in range(SH):
        k = y / SH
        s.fill((int(66 - 30 * k), int(132 - 38 * k), int(196 - 40 * k)), (0, y, SW, 1))
    for _ in range(60):
        x, y = rnd.randint(0, SW), rnd.randint(0, SH)
        D.line(s, (120, 175, 225), (x, y), (x + rnd.randint(8, 22), y), 1)

    def land(x):
        k = max(0.0, min(1.0, (x - 100) / 760))
        stops = ((120, 186, 96), (150, 172, 112), (112, 74, 104))
        if k < 0.5:
            a, b, f = stops[0], stops[1], k / 0.5
        else:
            a, b, f = stops[1], stops[2], (k - 0.5) / 0.5
        return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))

    pts = []
    for a, b in MAP_EDGES:
        for i in range(0, 31):
            pts.append(edge_point(a, b, i / 30))
    pts += list(MAP_NODES.values()) + [SHOP_POS]
    for px, py in pts:
        D.circle(s, (232, 218, 168), (int(px), int(py)), 88)
    for px, py in pts:
        D.circle(s, land(px), (int(px), int(py)), 80)
    # снег у ледяных пиков (узел 4)
    for _ in range(14):
        D.circle(s, (240, 247, 255), (int(450 + rnd.randint(-70, 70)), int(440 + rnd.randint(-45, 45))), rnd.randint(14, 26))
    # лава у узла 5
    D.polygon(s, (220, 90, 30), [(690, 400), (750, 420), (770, 470), (700, 480), (670, 440)])
    D.polygon(s, (255, 170, 60), [(700, 415), (740, 430), (750, 455), (705, 462)])

    def near_road(x, y, r):
        return any(math.hypot(x - px, y - py) < r for px, py in pts if (px, py) in set(MAP_NODES.values()) or True)

    road = [edge_point(a, b, i / 30) for a, b in MAP_EDGES for i in range(31)]
    nodes = list(MAP_NODES.values()) + [SHOP_POS]
    for _ in range(260):
        x, y = rnd.randint(30, SW - 30), rnd.randint(50, SH - 30)
        if any(math.hypot(x - px, y - py) < 78 for px, py in pts) and not any(math.hypot(x - px, y - py) < 34 for px, py in road) \
                and not any(math.hypot(x - px, y - py) < 52 for px, py in nodes) and not (660 < x < 790 and 390 < y < 490):
            if x < 360:
                D.circle(s, (46, 120, 60), (x, y), 9)
                D.circle(s, (70, 150, 80), (x - 2, y - 2), 5)
            elif x < 600:
                D.polygon(s, (60, 110, 100), [(x, y - 14), (x - 8, y + 4), (x + 8, y + 4)])
            else:
                D.polygon(s, (60, 30, 60), [(x, y - 14), (x - 6, y + 4), (x + 6, y + 4)])
    for a, b in MAP_EDGES:
        ps = [edge_point(a, b, i / 40) for i in range(41)]
        D.lines(s, (92, 66, 40), False, ps, 16)
        D.lines(s, (232, 206, 150), False, ps, 11)
    for a, b in MAP_EDGES:
        for i in range(0, 40, 2):
            p0, p1 = edge_point(a, b, i / 40), edge_point(a, b, (i + 1) / 40)
            D.line(s, (200, 170, 112), p0, p1, 2)
    return s


# ---------------------------------------------------------------- игра ------
class Input:
    def __init__(self):
        self.held = set()
        self.pressed = set()


def default_prog():
    return {"done": [], "gold": 0, "up": {"boots": 0, "vit": 0, "cd": 0}, "shard": False, "hero": 0, "coins": 0, "lives": 3}


SHOP = [
    ("boots", "Boots of Speed", "+8% к скорости (до 3 уровней)", 200, 3),
    ("vit", "Vitality Booster", "+1 к максимуму здоровья (до 3)", 300, 3),
    ("cd", "Octarine Essence", "−20% к перезарядке способностей (до 2)", 500, 2),
    ("shard", "Aghanim's Shard", "Следующий уровень начнётся с шардом", 400, 1),
    ("life", "Aegis of the Immortal", "+1 жизнь (до 9)", 350, 9),
]


class Game:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else {"bloom": True}
        self.bloom_on = bool(self.settings.get("bloom", True))
        self.exit_p = 0.0
        self.state = "title"
        self.t = 0
        self.sel = 0
        self.trans = None
        self.prog = self.load()
        self.node = 1
        self.walk = None
        self.shop_sel = 0
        self.music = Music()
        self.banner = None
        self.cur_held = set()
        self.map_surf = None
        self.vig = None
        self.amb = []
        self.confetti = []
        self.msg_t = 0
        self.msg = ""
        self.boss_won = False
        self.sel = self.prog.get("hero", 0) % len(HEROES)
        self.lives = self.prog.get("lives", 3)
        self.coins = self.prog.get("coins", 0)
        self.node = self.next_node()

    # -- сохранение
    def load(self):
        p = default_prog()
        try:
            with open(os.path.join(save_dir(), "save.json"), encoding="utf-8") as f:
                d = json.load(f)
            for k in p:
                if k in d:
                    p[k] = d[k]
            for k in ("boots", "vit", "cd"):
                p["up"].setdefault(k, 0)
        except Exception:
            pass
        return p

    def save(self):
        self.prog["hero"] = self.sel
        self.prog["lives"] = self.lives
        self.prog["coins"] = self.coins
        try:
            with open(os.path.join(save_dir(), "save.json"), "w", encoding="utf-8") as f:
                json.dump(self.prog, f)
        except Exception:
            pass

    def new_game(self):
        self.prog = default_prog()
        self.lives = 3
        self.coins = 0
        self.node = 1
        self.save()

    def next_node(self):
        done = set(self.prog["done"])
        for n in range(1, 7):
            if n not in done and self.unlocked(n):
                return n
        return 6

    def unlocked(self, n):
        if n == 1:
            return True
        done = set(self.prog["done"])
        return any(m in done for m in neighbors(n) if m < n)

    # -- переходы
    def goto(self, fn):
        if self.trans is None:
            self.trans = {"ph": "out", "t": 0, "fn": fn}

    def flash_msg(self, m):
        self.msg = m
        self.msg_t = 120

    def announce(self, msg, col=(255, 220, 90)):
        self.banner = [msg, 150, col]

    # -- запуск уровня
    def start_level(self, node):
        self.lv_node = node
        self.lv_idx = node - 1
        self.world = World(self.lv_idx)
        self.p = Player(self.sel, 2 * T, 13 * T, self.prog)
        if self.prog.get("shard"):
            self.prog["shard"] = False
            self.save()
        self.enemies = [Enemy(k, tx, ty) for k, tx, ty in self.world.enemy_spawns]
        self.projs = []
        self.drops = []
        self.fx = []
        self.parts = []
        self.bumps = {}
        self.shake = 0
        self.streak = 0
        self.last_kill = -999
        self.tick = 0
        self.cam = 0
        self.boss_dead = False
        self.state = "play"
        self.banner = None
        self.gold_start = self.prog["gold"]
        self.coins_start = self.coins
        self.first_blood = False
        self.spawn_amb()
        self.music.play("boss" if self.lv_idx == 5 else "level")
        if self.p.shard:
            self.announce("Aghanim's Shard!", (120, 220, 255))

    def rebuild_gfx(self):
        """Пересоздаёт все картинки после смены разрешения рендера."""
        self.map_surf = None
        self.vig = None
        w = getattr(self, "world", None)
        if w is not None:
            w.build_gfx()

    def spawn_amb(self):
        rnd = random.Random(3)
        self.amb = [[rnd.uniform(0, SW), rnd.uniform(0, SH), rnd.uniform(-0.3, 0.3), rnd.uniform(0.2, 1.0), rnd.uniform(1, 3), rnd.uniform(0, 6.28)] for _ in range(50)]

    # -- вспомогательное
    def ring(self, x, y, r1, col, life=22, w=4):
        self.fx.append(dict(k="ring", x=x, y=y, r=r1, t=0, T=life, col=col, w=w))

    def pop(self, x, y, msg, col=(255, 230, 90)):
        self.fx.append(dict(k="txt", x=x, y=y, s=msg, t=0, T=50, col=col))

    def burst(self, x, y, col, n=10, sp=3.0):
        for _ in range(n):
            a = random.random() * 6.283
            v = random.random() * sp + 0.5
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v - 1, random.randint(18, 34), col, random.randint(2, 4)])

    def add_gold(self, g, x=None, y=None):
        self.prog["gold"] += g

    def add_coin(self, x, y):
        self.prog["gold"] += 10
        self.coins += 1
        sfx("coin")
        self.pop(x, y - 10, "+10")
        if self.coins >= 100:
            self.coins -= 100
            self.lives = min(9, self.lives + 1)
            sfx("oneup")
            self.announce("1UP!  +1 жизнь", (120, 255, 140))

    def hurt_player(self, kx=0, force=False):
        p = self.p
        if not force and (p.inv > 0 or p.ghost > 0):
            return
        if p.shard and not force:
            p.shard = False
            p.inv = 100
            p.vy = -6
            p.vx = kx * 4
            sfx("hit")
            self.shake = max(self.shake, 6)
            self.burst(p.cx, p.cy, (120, 220, 255), 16, 4)
            self.pop(p.cx, p.y - 8, "Шард потерян", (140, 225, 255))
            return
        p.hp -= 1
        p.inv = 90
        p.vy = -7
        p.vx = kx * 5
        sfx("hit")
        self.shake = max(self.shake, 8)
        self.burst(p.cx, p.cy, (230, 60, 60), 8)
        if p.hp <= 0:
            self.die()

    def die(self):
        self.p.shard = False
        if self.lives > 0:
            self.lives -= 1
            self.state = "dead"
        else:
            self.state = "gameover"
        self.save()

    def kill_enemy(self, e):
        e.alive = False
        sfx("stomp")
        self.burst(e.cx, e.cy, (255, 200, 70), 14, 4)
        self.prog["gold"] += 25 if e.kind != "B" else 500
        self.pop(e.cx, e.y - 6, "+25" if e.kind != "B" else "+500")
        if e.kind == "B":
            self.boss_dead = True
            self.announce("Рошан повержен!", (255, 200, 60))
            self.shake = 20
            return
        if self.tick - self.last_kill < 200:
            self.streak += 1
        else:
            self.streak = 1
        self.last_kill = self.tick
        names = {2: "Double Kill!", 3: "Triple Kill!", 4: "Ultra Kill!", 5: "Rampage!"}
        if not self.first_blood:
            self.first_blood = True
            self.announce("First Blood!", (255, 80, 60))
        elif self.streak >= 2:
            self.announce(names.get(min(self.streak, 5)), (255, 140, 40))

    def damage_enemy(self, e, dmg):
        if not e.alive:
            return False
        if e.kind == "B":
            if e.inv > 0:
                return False
            e.hp -= dmg
            e.inv = 40
            e.flash = 30
            sfx("hit")
            self.burst(e.cx, e.cy, (255, 220, 120), 8)
            if e.hp <= 0:
                self.kill_enemy(e)
            return True
        e.hp -= dmg
        e.flash = 8
        if e.hp <= 0:
            self.kill_enemy(e)
        return True

    # -- блоки и предметы
    def hit_block(self, tx, ty):
        w = self.world
        ch = w.tile(tx, ty)
        if ch == "?":
            content = w.q.get((tx, ty), "coin")
            w.g[ty][tx] = "%"
            self.bumps[(tx, ty)] = 12
            sfx("bump")
            x, y = tx * T + T // 2, ty * T
            if content == "coin":
                self.add_coin(x, y - 10)
            elif content == "coins":
                for k in range(5):
                    self.add_coin(x + (k - 2) * 12, y - 10 - k * 6)
            elif content in ("shard", "salve"):
                b = Body(tx * T + (T - 22) / 2, ty * T - 22, 22, 22)
                b.kind = content
                b.vy = -7
                b.vx = 1.4 if content == "shard" else 0
                b.t = 0
                b.born = 10
                self.drops.append(b)
            self.burst(x, y, (255, 220, 90), 8)
        elif ch == "=":
            self.bumps[(tx, ty)] = 8
            sfx("bump")

    def collect_drop(self, d):
        p = self.p
        if d.kind == "shard":
            if p.shard:
                self.prog["gold"] += 100
                self.pop(d.cx, d.y - 8, "+100")
                sfx("coin")
            else:
                p.shard = True
                sfx("shard")
                self.announce("Aghanim's Shard!", (120, 220, 255))
                self.ring(p.cx, p.cy, 80, (120, 220, 255), 28, 6)
                self.burst(p.cx, p.cy, (150, 230, 255), 24, 5)
                self.pop(p.cx, p.y - 10, SHARD_TEXT[p.hid].split(":")[0], (150, 230, 255))
        else:
            if p.hp < p.maxhp:
                p.hp += 1
                self.pop(d.cx, d.y - 8, "+1 HP", (120, 255, 140))
            else:
                self.prog["gold"] += 50
                self.pop(d.cx, d.y - 8, "+50", (255, 230, 90))
            sfx("coin")

    # -- способности
    def cast(self, n):
        p = self.p
        f = p.facing
        hid = p.hid
        if p.cd[n] > 0:
            return
        base = p.hero["ab"][n][2]
        p.cdmax[n] = max(1, int(base * p.cd_scale))
        p.cd[n] = p.cdmax[n]
        p.cast_t = 14
        sh = p.shard
        if hid == "pudge":
            if n == 0:
                self.projs.append(dict(k="hook", x=p.cx, y=p.y + 24, vx=14.0 * f, vy=0, life=int(26 * (1.5 if sh else 1)), own="p", dmg=2 if sh else 1))
                sfx("hook")
            else:
                p.rot = 220 if sh else 150
                p.rot_r = 135 if sh else 95
                sfx("magic")
        elif hid == "invoker":
            if n == 0:
                rad = 116 if sh else 80
                self.projs.append(dict(k="meteor", x=p.cx + f * 14, y=p.y + 14, vx=7.0 * f, vy=-5.0, life=100, own="p", rad=rad))
                if sh:
                    self.projs.append(dict(k="meteor", x=p.cx + f * 14, y=p.y + 14, vx=5.0 * f, vy=-8.5, life=100, own="p", rad=rad))
                sfx("magic")
            else:
                p.ghost = 270 if sh else 180
                sfx("magic")
                self.ring(p.cx, p.cy, 60, (170, 120, 255))
        elif hid == "meepo":
            if n == 0:
                self.poof(f)
            else:
                self.projs.append(dict(k="net", x=p.cx, y=p.cy, vx=10.0 * f, vy=0, life=45, own="p", area=70 if sh else 0, dur=270 if sh else 180))
                sfx("hook")
        else:
            if n == 0:
                self.slam(205 if sh else 150, 3 if sh else 2, stun=sh)
            else:
                p.totem = 450 if sh else 300
                sfx("magic")
                self.ring(p.cx, p.cy, 70, (255, 170, 60))

    def poof(self, f):
        p, w = self.p, self.world
        sx = p.cx
        self.ring(sx, p.cy, 50, (120, 200, 255))
        dist = 255 if p.shard else 170
        moved = 0
        while moved < dist:
            p.x += f * 5
            if any(w.solid(tx, ty) for tx in range(int(p.x // T), int((p.x + p.w - 0.01) // T) + 1)
                   for ty in range(int(p.y // T), int((p.y + p.h - 0.01) // T) + 1)):
                p.x -= f * 5
                break
            moved += 5
        p.vx = 0
        p.inv = max(p.inv, 15)
        box = pygame.Rect(int(min(sx, p.cx) - 30), int(p.y - 10), int(abs(p.cx - sx) + 60), p.h + 20)
        for e in self.enemies:
            if e.alive and box.colliderect(e.rect):
                self.damage_enemy(e, 3 if p.shard else 2)
        self.ring(p.cx, p.cy, 60, (120, 200, 255))
        self.burst(p.cx, p.cy, (140, 210, 255), 12)
        sfx("magic")

    def slam(self, radius, dmg, stun=False):
        p = self.p
        cx, cy = p.cx, p.y + p.h
        self.ring(cx, cy, radius, (255, 190, 80), 26, 6)
        self.ring(cx, cy, radius * 0.6, (255, 240, 160), 20, 4)
        self.burst(cx, cy, (190, 140, 90), 16, 4)
        self.shake = max(self.shake, 14)
        sfx("boom")
        for e in self.enemies:
            if e.alive and math.hypot(e.cx - cx, e.cy - cy) < radius + e.w / 2 and abs(e.cy - cy) < 130:
                self.damage_enemy(e, dmg)
                if stun and e.alive and e.kind != "B":
                    e.stun = 90

    def explode(self, x, y, rad=80):
        self.ring(x, y, rad, (255, 140, 40), 24, 6)
        self.burst(x, y, (255, 160, 50), 18, 4)
        self.shake = max(self.shake, 7)
        sfx("boom")
        for e in self.enemies:
            if e.alive and math.hypot(e.cx - x, e.cy - y) < rad + e.w / 2:
                self.damage_enemy(e, 2)

    # -- шаг игры
    def step(self, inp):
        self.tick += 1
        p, w = self.p, self.world
        held, pressed = inp.held, inp.pressed
        ax = (1 if "right" in held else 0) - (1 if "left" in held else 0)
        if ax:
            p.facing = ax
        k = 0.28 if p.on_ground else 0.14
        p.vx += (ax * p.speed - p.vx) * k
        if abs(p.vx) < 0.05 and not ax:
            p.vx = 0
        p.anim += abs(p.vx) * 0.12
        if "jump" in pressed:
            p.jbuf = 7
        p.jbuf = max(0, p.jbuf - 1)
        p.coyote = 7 if p.on_ground else max(0, p.coyote - 1)
        if p.on_ground:
            p.air_jumps = 1 if p.hid == "meepo" else 0
        if p.jbuf > 0:
            if p.coyote > 0:
                power = p.jump
                if p.totem > 0:
                    power = 17.0
                    p.totem_jump = True
                p.vy = -power
                p.jbuf = 0
                p.coyote = 0
                p.sq = 1.22
                sfx("jump")
            elif p.air_jumps > 0:
                p.vy = -p.jump * 0.95
                p.air_jumps -= 1
                p.jbuf = 0
                p.sq = 1.2
                sfx("jump")
                self.burst(p.cx, p.y + p.h, (140, 210, 255), 6)
        if "jump" not in held and p.vy < -3.0:
            p.vy *= 0.86
        p.vy = min(p.vy + GRAV, MAXFALL)
        p.pb = p.y + p.h
        p.was_ground = p.on_ground
        w.move(p, p.vx, p.vy)
        if p.bump:
            self.hit_block(*p.bump)
        if p.on_ground and not p.was_ground:
            p.sq = 0.8
            self.burst(p.cx, p.y + p.h, (210, 200, 180), 4, 1.6)
            if p.totem_jump:
                p.totem_jump = False
                self.slam(120, 2)
        p.sq += (1.0 - p.sq) * 0.2
        if p.on_ground:
            l = w.solid(int((p.x + 2) // T), int((p.y + p.h + 2) // T))
            r = w.solid(int((p.x + p.w - 3) // T), int((p.y + p.h + 2) // T))
            if l and r:
                p.safe = (p.x, p.y)
        for i in range(2):
            p.cd[i] = max(0, p.cd[i] - 1)
        p.inv = max(0, p.inv - 1)
        p.ghost = max(0, p.ghost - 1)
        p.totem = max(0, p.totem - 1)
        p.cast_t = max(0, p.cast_t - 1)
        if "a1" in pressed:
            self.cast(0)
        if "a2" in pressed:
            self.cast(1)
        if p.rot > 0:
            p.rot -= 1
            if p.rot % 20 == 0:
                for e in self.enemies:
                    if e.alive and math.hypot(e.cx - p.cx, e.cy - p.cy) < p.rot_r:
                        self.damage_enemy(e, 1)
            if p.rot % 5 == 0:
                self.parts.append([p.cx + random.randint(-int(p.rot_r * .5), int(p.rot_r * .5)), p.cy + random.randint(-30, 30), 0, -0.6, 28, (110, 200, 80), 5])
        if p.y > ROWS * T + 60:
            p.x, p.y = p.safe
            p.vx = p.vy = 0
            self.hurt_player(0, force=True)
            if self.state != "play":
                return
        pr = p.rect
        for c in w.coins:
            if not c[2] and abs(c[0] - p.cx) < 22 and abs(c[1] - p.cy) < 32:
                c[2] = True
                self.add_coin(c[0], c[1])
        for it in w.items:
            if not it[2] and abs(it[0] - p.cx) < 24 and abs(it[1] - p.cy) < 34 and p.hp < p.maxhp:
                it[2] = True
                p.hp += 1
                sfx("coin")
                self.pop(it[0], it[1] - 10, "+1 HP", (120, 255, 140))
        for d in self.drops:
            d.t += 1
            d.vy = min(d.vy + GRAV * 0.8, MAXFALL)
            if d.kind == "shard":
                if w.move(d, d.vx, d.vy):
                    d.vx *= -1
                if d.on_ground and d.born <= 0:
                    pass
            else:
                w.move(d, 0, d.vy)
            d.born -= 1
            if d.y > ROWS * T + 60:
                d.kind = "gone"
            elif d.kind != "gone" and pr.colliderect(d.rect):
                self.collect_drop(d)
                d.kind = "gone"
        self.drops = [d for d in self.drops if d.kind != "gone"]
        for ty in range(int(p.y // T), int((p.y + p.h - 0.01) // T) + 1):
            for tx in range(int(p.x // T), int((p.x + p.w - 0.01) // T) + 1):
                if w.tile(tx, ty) == "^":
                    sp = pygame.Rect(tx * T + 4, ty * T + 14, T - 8, T - 14)
                    if pr.colliderect(sp):
                        self.hurt_player(0)
                        p.vy = -9
                        if self.state != "play":
                            return
        for e in self.enemies:
            if e.alive:
                self.update_enemy(e)
        self.enemies_contact()
        self.update_projs()
        if self.state != "play":
            return
        if w.flag and (not w.flag_needs_boss or self.boss_dead):
            if pr.colliderect(w.flag):
                self.finish_level()
        tx = p.cx - SW * 0.42 + p.vx * 12
        self.cam += (max(0, min(w.px - SW, tx)) - self.cam) * 0.12
        self.shake = max(0, self.shake - 1)
        for f in self.fx:
            f["t"] += 1
        self.fx = [f for f in self.fx if f["t"] < f["T"]]
        for pt in self.parts:
            pt[0] += pt[2]
            pt[1] += pt[3]
            pt[3] += 0.12
            pt[4] -= 1
        self.parts = [pt for pt in self.parts if pt[4] > 0]
        for key in list(self.bumps):
            self.bumps[key] -= 1
            if self.bumps[key] <= 0:
                del self.bumps[key]
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None

    def finish_level(self):
        self.state = "levelwin"
        sfx("win")
        bonus = 100 + 30 * self.p.hp
        self.bonus = bonus
        self.prog["gold"] += bonus
        if self.lv_node not in self.prog["done"]:
            self.prog["done"].append(self.lv_node)
        self.save()
        self.confetti = [[random.randint(0, SW), random.randint(-SH, 0), random.choice([(255, 90, 90), (255, 220, 90), (90, 200, 255), (130, 255, 130)]), random.random() * 2 + 1] for _ in range(90)]

    def update_enemy(self, e):
        p, w = self.p, self.world
        e.t += 1
        e.flash = max(0, e.flash - 1)
        e.inv = max(0, e.inv - 1)
        if e.frozen > 0:
            e.frozen -= 1
        if e.stun > 0:
            e.stun -= 1
        if e.kind == "e":
            if e.frozen == 0 and e.stun == 0:
                ahead = int((e.cx + e.dir * (e.w / 2 + 4)) // T)
                below = int((e.y + e.h + 3) // T)
                if e.on_ground and not w.solid(ahead, below):
                    e.dir *= -1
                e.vx = e.dir * (1.0 + 0.15 * self.lv_idx)
            else:
                e.vx = 0
            e.vy = min(e.vy + GRAV, MAXFALL)
            if w.move(e, e.vx, e.vy):
                e.dir *= -1
            if e.y > ROWS * T + 60:
                e.alive = False
        elif e.kind == "r":
            e.vy = min(e.vy + GRAV, MAXFALL)
            w.move(e, 0, e.vy)
            e.dir = 1 if p.cx > e.cx else -1
            e.cd -= 1
            if e.cd <= 0 and e.frozen == 0 and e.stun == 0 and abs(p.cx - e.cx) < 440 and abs(p.cy - e.cy) < 220:
                e.cd = max(70, 120 - 8 * self.lv_idx)
                dx, dy = p.cx - e.cx, p.cy - e.cy
                d = max(1.0, math.hypot(dx, dy))
                self.projs.append(dict(k="bolt", x=e.cx, y=e.y + 8, vx=dx / d * 4.2, vy=dy / d * 4.2, life=140, own="e"))
        else:
            self.update_boss(e)

    def update_boss(self, e):
        p, w = self.p, self.world
        if not e.awake:
            if abs(p.cx - e.cx) < 650:
                e.awake = True
                self.announce("Рошан проснулся!", (255, 120, 60))
            e.vy = min(e.vy + GRAV, MAXFALL)
            w.move(e, 0, e.vy)
            return
        enraged = e.hp <= e.maxhp // 2
        e.dir = 1 if p.cx > e.cx else -1
        e.jump_cd -= 1
        if e.frozen == 0:
            if e.on_ground:
                if e.jumping:
                    e.jumping = False
                    e.vx = 0
                    self.ring(e.cx, e.y + e.h, 170, (255, 160, 70), 26, 6)
                    self.shake = max(self.shake, 14)
                    sfx("boom")
                    if p.on_ground and abs(p.cx - e.cx) < 190:
                        self.hurt_player(1 if p.cx > e.cx else -1)
                e.vx = e.dir * (1.9 if enraged else 1.3)
                if e.jump_cd <= 0:
                    e.jump_cd = 95 if enraged else 150
                    e.vy = -14.5
                    e.vx = max(-4.5, min(4.5, (p.cx - e.cx) / 22))
                    e.jumping = True
            else:
                e.vx *= 0.995
        else:
            e.vx = 0
        e.vy = min(e.vy + GRAV, MAXFALL)
        w.move(e, e.vx, e.vy)

    def enemies_contact(self):
        p = self.p
        if p.ghost > 0 or self.state != "play":
            return
        pr = p.rect.inflate(-6, -4)
        for e in self.enemies:
            if not e.alive or not e.awake:
                continue
            er = e.rect.inflate(-4, -2) if e.kind != "B" else e.rect.inflate(-18, -10)
            if not pr.colliderect(er):
                continue
            stomp = p.vy > 0.5 and p.pb <= e.y + 16
            if stomp:
                if e.kind == "B":
                    self.damage_enemy(e, 1)
                    p.vy = -11
                    p.vx = 5 * (1 if p.cx > e.cx else -1)
                else:
                    self.damage_enemy(e, 1)
                    p.vy = -10.5 if "jump" not in self.cur_held else -13
                p.sq = 0.85
                self.ring(p.cx, p.y + p.h, 30, (255, 255, 255), 14, 3)
            elif e.frozen > 0 and e.kind != "B":
                continue
            else:
                self.hurt_player(1 if p.cx > e.cx else -1)
                if self.state != "play":
                    return

    def update_projs(self):
        w, p = self.world, self.p
        keep = []
        for q in self.projs:
            q["life"] -= 1
            dead = q["life"] <= 0
            if q["k"] == "meteor":
                q["vy"] += 0.3
            q["x"] += q["vx"]
            q["y"] += q["vy"]
            if w.solid(int(q["x"] // T), int(q["y"] // T)):
                dead = True
                if q["k"] == "meteor":
                    self.explode(q["x"] - q["vx"], q["y"] - q["vy"], q.get("rad", 80))
                    q["life"] = 1
            elif q["k"] == "bolt":
                if p.ghost == 0 and p.rect.collidepoint(q["x"], q["y"]):
                    self.hurt_player(1 if q["vx"] > 0 else -1)
                    dead = True
                    if self.state != "play":
                        return
            elif q["own"] == "p" and not dead:
                for e in self.enemies:
                    if not e.alive or (e.kind == "B" and not e.awake):
                        continue
                    if e.rect.inflate(10, 10).collidepoint(q["x"], q["y"]):
                        if q["k"] == "hook":
                            self.damage_enemy(e, q.get("dmg", 1))
                            if e.alive and e.kind != "B":
                                nx = p.cx + p.facing * (p.w / 2 + e.w / 2 + 4) - e.w / 2
                                if not w.solid(int((nx + e.w / 2) // T), int((e.y + e.h / 2) // T)):
                                    e.x = nx
                                e.stun = 60
                        elif q["k"] == "net":
                            dur = q.get("dur", 180)
                            hit = [e]
                            if q.get("area"):
                                hit = [o for o in self.enemies if o.alive and math.hypot(o.cx - e.cx, o.cy - e.cy) < q["area"] + o.w / 2]
                            for o in hit:
                                o.frozen = dur if o.kind != "B" else dur // 3
                            self.ring(e.cx, e.cy, 40 + q.get("area", 0), (150, 220, 255), 18, 3)
                        elif q["k"] == "meteor":
                            self.explode(q["x"], q["y"], q.get("rad", 80))
                            q["life"] = 1
                        dead = True
                        break
            if dead and q["k"] == "meteor" and q["life"] == 0:
                self.explode(q["x"], q["y"], q.get("rad", 80))
            if not dead:
                keep.append(q)
        self.projs = keep

    # -- карта мира
    def map_input(self, pr):
        if self.walk:
            return
        if "enter" in pr and self.unlocked(self.node):
            sfx("select")
            node = self.node
            self.goto(lambda: self.start_level(node))
            return
        if "shop" in pr:
            sfx("select")
            self.goto(self.open_shop)
            return
        if "hero" in pr:
            self.sel = (self.sel + 1) % len(HEROES)
            sfx("select")
            self.save()
            return
        if "back" in pr:
            self.goto(self.to_title)
            return
        dirs = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
        for k, (dx, dy) in dirs.items():
            if k in pr:
                best, bs = None, 0.45
                x0, y0 = MAP_NODES[self.node]
                for n in neighbors(self.node):
                    if not self.unlocked(n):
                        continue
                    x1, y1 = MAP_NODES[n]
                    d = math.hypot(x1 - x0, y1 - y0)
                    dot = ((x1 - x0) * dx + (y1 - y0) * dy) / d
                    if dot > bs:
                        best, bs = n, dot
                if best:
                    self.walk = [self.node, best, 0.0]
                    sfx("select")
                else:
                    sfx("nope")
                break

    def open_shop(self):
        self.state = "shop"
        self.shop_sel = 0
        self.music.play("map")

    def to_title(self):
        self.state = "title"
        self.music.play("map")

    def to_map(self):
        self.state = "map"
        self.walk = None
        self.node = self.lv_node if hasattr(self, "lv_node") and self.state != "x" else self.node
        self.music.play("map")

    def shop_price(self, key):
        for k, name, desc, price, mx in SHOP:
            if k == key:
                lvl = self.prog["up"].get(k, 0) if k in self.prog["up"] else 0
                return price * (lvl + 1) if k in ("boots", "vit", "cd") else price

    def shop_level(self, key):
        if key in self.prog["up"]:
            return self.prog["up"][key]
        if key == "shard":
            return 1 if self.prog.get("shard") else 0
        return self.lives

    def buy(self, key):
        mx = next(m for k, _, _, _, m in SHOP if k == key)
        lvl = self.shop_level(key)
        price = self.shop_price(key)
        if (key == "life" and lvl >= mx) or (key != "life" and lvl >= mx) or self.prog["gold"] < price:
            sfx("nope")
            self.flash_msg("Нельзя купить" if lvl >= mx else "Не хватает золота")
            return
        self.prog["gold"] -= price
        if key in self.prog["up"]:
            self.prog["up"][key] += 1
        elif key == "shard":
            self.prog["shard"] = True
        else:
            self.lives += 1
        sfx("buy")
        self.flash_msg("Куплено!")
        self.save()

    # -- общий апдейт
    def update(self, inp):
        self.t += 1
        self.cur_held = inp.held
        pr = inp.pressed
        if self.msg_t:
            self.msg_t -= 1
        if "mute" in pr:
            self.music.toggle()
        if "quality" in pr:
            self.bloom_on = not self.bloom_on
            self.settings["bloom"] = self.bloom_on
            save_settings(self.settings) if "fullscreen" in self.settings else None
            self.flash_msg("Свечение: " + ("включено" if self.bloom_on else "выключено"))
        if self.trans:
            tr = self.trans
            tr["t"] += 1
            if tr["ph"] == "out" and tr["t"] >= 14:
                tr["fn"]()
                tr["ph"], tr["t"] = "in", 0
            elif tr["ph"] == "in" and tr["t"] >= 14:
                self.trans = None
            return
        st = self.state
        if st == "title":
            self.music.play("map")
            if "left" in pr:
                self.sel = (self.sel - 1) % len(HEROES)
                sfx("select")
            if "right" in pr:
                self.sel = (self.sel + 1) % len(HEROES)
                sfx("select")
            if "new" in pr:
                self.new_game()
                self.flash_msg("Новая игра: прогресс сброшен")
            if "enter" in pr or "jump" in pr:
                self.save()
                self.node = self.next_node() if self.node not in range(1, 7) else self.node
                sfx("select")
                self.goto(self.to_map)
        elif st == "map":
            self.music.play("map")
            if self.walk:
                a, b, t = self.walk
                t += 0.025
                if t >= 1:
                    self.node = b
                    self.walk = None
                else:
                    self.walk[2] = t
            self.map_input(pr)
        elif st == "shop":
            if "up" in pr:
                self.shop_sel = (self.shop_sel - 1) % len(SHOP)
                sfx("select")
            if "down" in pr:
                self.shop_sel = (self.shop_sel + 1) % len(SHOP)
                sfx("select")
            if "enter" in pr:
                self.buy(SHOP[self.shop_sel][0])
            if "back" in pr or "shop" in pr:
                self.goto(self.to_map)
        elif st == "play":
            if "pause" in pr or "back" in pr:
                self.state = "pause"
            else:
                self.step(inp)
        elif st == "pause":
            if "pause" in pr:
                self.state = "play"
            elif "back" in pr:
                self.prog["gold"] = self.gold_start
                self.coins = self.coins_start
                self.goto(self.to_map)
        elif st in ("dead", "gameover"):
            self.shake = 0
            if "enter" in pr or "restart" in pr:
                self.prog["gold"] = self.gold_start
                self.coins = self.coins_start
                if st == "dead":
                    n = self.lv_node
                    self.goto(lambda: self.start_level(n))
                else:
                    self.lives = 3
                    self.save()
                    self.goto(self.to_map)
            elif "back" in pr:
                self.prog["gold"] = self.gold_start
                self.coins = self.coins_start
                self.goto(self.to_map)
        elif st == "levelwin":
            for c in self.confetti:
                c[1] += c[3]
                if c[1] > SH:
                    c[1] = -10
            if "enter" in pr or "jump" in pr:
                if self.lv_node == 6:
                    self.goto(self.to_ending)
                else:
                    done_node = self.lv_node
                    self.goto(lambda: self.after_level(done_node))
        elif st == "ending":
            for c in self.confetti:
                c[1] += c[3]
                if c[1] > SH:
                    c[1] = -10
            if "enter" in pr:
                self.goto(self.to_title)

    def after_level(self, node):
        self.state = "map"
        self.walk = None
        self.node = node
        self.music.play("map")

    def to_ending(self):
        self.state = "ending"
        self.confetti = [[random.randint(0, SW), random.randint(-SH, 0), random.choice([(255, 90, 90), (255, 220, 90), (90, 200, 255), (130, 255, 130)]), random.random() * 2 + 1] for _ in range(120)]

    # ----------------------------------------------------------- рисование --
    def draw(self, s):
        st = self.state
        if st == "title":
            self.draw_title(s)
        elif st == "map":
            self.draw_map(s)
        elif st == "shop":
            self.draw_map(s)
            self.draw_shop(s)
        elif st == "ending":
            self.draw_ending(s)
        else:
            self.draw_play(s)
        if self.msg_t:
            panel(s, (SW // 2 - 190, 480, 380, 38), 190, 10)
            text(s, self.msg, F_S, (255, 235, 160), (SW // 2, 499), True, shadow=False, alpha=min(255, self.msg_t * 8))
        if self.trans:
            tr = self.trans
            k = min(1.0, tr["t"] / 14)
            iris(s, k if tr["ph"] == "out" else 1 - k)
        if self.exit_p > 0:
            panel(s, (SW // 2 - 170, SH // 2 - 70, 340, 140), 220, 16, border=(255, 220, 90, 255))
            text(s, "Выход из игры", F_M, (255, 255, 255), (SW // 2, SH // 2 - 38), True)
            rect = pygame.Rect(SW // 2 - 28, SH // 2 - 14, 56, 56)
            D.circle(s, (60, 66, 90), rect.center, 28, 5)
            if self.exit_p > 0.02:
                D.arc(s, (255, 220, 90), rect, math.pi / 2 - 2 * math.pi * self.exit_p, math.pi / 2, 6)
            text(s, "держите Esc", F_XS, (200, 210, 235), (SW // 2, SH // 2 + 58), True, shadow=False)

    def overlay(self, s, rgba):
        o = HSurf((SW, SH), pygame.SRCALPHA)
        o.fill(rgba)
        s.blit(o, (0, 0))

    def draw_ambient(self, s, th, cam):
        amb = th["amb"]
        for a in self.amb:
            a[0] += a[2] * (3 if amb == "snow" else 1)
            a[1] += a[3] * (2.2 if amb in ("snow", "ember") else 0.3) * (-1 if amb in ("ember", "fly") else 1)
            a[5] += 0.04
            if a[1] > SH + 10:
                a[1] = -10
            if a[1] < -10:
                a[1] = SH + 10
            a[0] %= SW
            x, y = int(a[0]), int(a[1])
            if amb == "snow":
                D.circle(s, (255, 255, 255), (x, y), int(a[4]))
            elif amb == "ember":
                add_glow(s, x, y, 7, (200, 90, 20))
            elif amb == "fly":
                if math.sin(a[5]) > 0:
                    add_glow(s, x, y, 9, (120, 140, 40) if th is THEMES[0] else (130, 70, 150))
            else:
                add_glow(s, x, y, 5, (50, 70, 90))

    def draw_play(self, s):
        w, p = self.world, self.p
        th = w.theme
        ox = oy = 0
        if self.shake:
            ox = random.randint(-self.shake // 2, self.shake // 2)
            oy = random.randint(-self.shake // 3, self.shake // 3)
        cam = int(self.cam) + ox
        s.blit(w.sky, (0, 0))
        if self.lv_idx == 0:
            for k in range(6):
                x = (k * 260 - self.cam * 0.08 + self.t * 0.15) % (SW + 200) - 100
                D.ellipse(s, (255, 255, 255), (x, 50 + (k * 37) % 90, 110, 34))
                D.ellipse(s, (255, 255, 255), (x + 30, 38 + (k * 37) % 90, 70, 34))
        if self.lv_idx == 4:
            add_glow(s, SW // 2, SH - 20, 420, (110, 40, 10))
        for factor, surf in w.layers:
            s.blit(surf, (-self.cam * factor + ox, oy))
        for tx, ty, kind, ph, var in w.decor:
            dx = tx * T + T // 2 - cam
            if -60 < dx < SW + 60:
                draw_decor(s, kind, dx, ty * T + 6 + oy, self.t, ph, var)
        self.draw_tiles(s, cam, oy)
        for c in w.coins:
            if not c[2]:
                bob = math.sin((self.t + c[0]) * 0.1) * 3
                x, y = int(c[0] - cam), int(c[1] + bob + oy)
                if -20 < x < SW + 20:
                    add_glow(s, x, y, 18, (90, 70, 10))
                    wd = abs(math.cos((self.t + c[0]) * 0.07))
                    D.ellipse(s, (255, 205, 50), (x - int(8 * wd) - 1, y - 8, int(16 * wd) + 2, 16))
                    D.ellipse(s, (200, 140, 20), (x - int(8 * wd) - 1, y - 8, int(16 * wd) + 2, 16), 2)
        for it in w.items:
            if not it[2]:
                bob = math.sin((self.t + it[0]) * 0.08) * 3
                x, y = int(it[0] - cam), int(it[1] + bob + oy)
                self.draw_salve(s, x, y)
        for d in self.drops:
            x, y = int(d.cx - cam), int(d.cy + oy)
            if d.kind == "shard":
                add_glow(s, x, y, 34, (30, 90, 120))
                draw_crystal(s, x, y + int(math.sin(self.t * 0.15) * 2), 13, self.t)
            else:
                self.draw_salve(s, x, y)
        if w.flag and (not w.flag_needs_boss or self.boss_dead):
            f = w.flag_draw
            x = f.x - cam
            D.rect(s, (110, 110, 125), (x + 6, f.y + 40, 24, f.h - 40))
            D.polygon(s, (130, 130, 150), [(x + 2, f.y + 42), (x + 34, f.y + 42), (x + 18, f.y)])
            glow = 170 + int(math.sin(self.t * 0.1) * 60)
            D.circle(s, (80, min(255, glow), 255), (x + 18, f.y + 30), 8)
            add_glow(s, x + 18, f.y + 30, 50, (30, 70, 110))
        for e in self.enemies:
            if not e.alive:
                continue
            r = e.rect.move(-cam, oy)
            sh = HSurf((r.w + 10, 10), pygame.SRCALPHA)
            D.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
            s.blit(sh, (r.x - 5, r.bottom - 5))
            if e.kind == "e":
                draw_creep(s, r, e, self.t)
            elif e.kind == "r":
                draw_ranged(s, r, e, self.t, p.cx)
            else:
                draw_boss(s, r, e, self.t, e.hp <= e.maxhp // 2)
                bw = 320
                panel(s, (SW // 2 - bw // 2 - 8, 74, bw + 16, 28), 170, 8)
                D.rect(s, (30, 20, 20), (SW // 2 - bw // 2, 82, bw, 12), border_radius=5)
                D.rect(s, (226, 62, 50), (SW // 2 - bw // 2, 82, bw * max(0, e.hp) // e.maxhp, 12), border_radius=5)
                text(s, "РОШАН", F_XS, (255, 230, 200), (SW // 2, 67), True)
        for q in self.projs:
            x, y = int(q["x"] - cam), int(q["y"] + oy)
            if q["k"] == "hook":
                D.line(s, (170, 170, 175), (int(p.cx - cam), int(p.y + 24 + oy)), (x, y), 3)
                D.circle(s, (200, 200, 205), (x, y), 6)
                D.polygon(s, (230, 230, 235), [(x, y - 8), (x + 7 * (1 if q["vx"] > 0 else -1), y), (x, y + 8)])
            elif q["k"] == "meteor":
                add_glow(s, x, y, 40, (120, 50, 10))
                D.circle(s, (255, 90, 20), (x, y), 11)
                D.circle(s, (255, 200, 80), (x, y), 6)
                self.parts.append([q["x"], q["y"], random.uniform(-.5, .5), random.uniform(-.5, .5), 14, (255, 140, 40), 4])
            elif q["k"] == "net":
                D.circle(s, (170, 230, 255), (x, y), 10, 2)
                D.line(s, (170, 230, 255), (x - 8, y), (x + 8, y), 1)
                D.line(s, (170, 230, 255), (x, y - 8), (x, y + 8), 1)
            else:
                add_glow(s, x, y, 22, (80, 30, 120))
                D.circle(s, (190, 90, 255), (x, y), 7)
                D.circle(s, (255, 230, 255), (x, y), 3)
        self.draw_player(s, cam, oy)
        for pt in self.parts:
            D.circle(s, pt[5], (int(pt[0] - cam), int(pt[1] + oy)), pt[6])
        for f in self.fx:
            k = f["t"] / f["T"]
            if f["k"] == "ring":
                r = int(f["r"] * (0.2 + 0.8 * k))
                D.circle(s, f["col"], (int(f["x"] - cam), int(f["y"] + oy)), r, max(1, int(f["w"] * (1 - k))))
            else:
                text(s, f["s"], F_M, f["col"], (int(f["x"] - cam), int(f["y"] - 30 * k + oy)), True, alpha=int(255 * (1 - k * 0.6)))
        self.draw_ambient(s, th, cam)
        if self.bloom_on:
            bloom(s)
        if self.vig is None:
            self.vig = make_vignette()
        s.blit(self.vig, (0, 0))
        self.draw_hud(s)
        if self.banner:
            msg, t, col = self.banner
            a = min(1.0, t / 40)
            img = F_XL.render(msg, True, col)
            sh = F_XL.render(msg, True, (0, 0, 0))
            img.set_alpha(int(255 * a))
            sh.set_alpha(int(255 * a))
            r = img.get_rect(center=(SW // 2, 150 + (150 - t) // 6))
            s.blit(sh, r.move(3, 3))
            s.blit(img, r)
        if self.state == "dead":
            self.overlay(s, (90, 0, 0, 150))
            text(s, "Вы погибли", F_XL, (255, 90, 90), (SW // 2, 190), True)
            text(s, "You have been slain!", F_M, (255, 200, 200), (SW // 2, 245), True)
            text(s, f"Осталось жизней: {self.lives}", F_M, (255, 230, 160), (SW // 2, 290), True)
            text(s, "Enter — ещё раз     Esc — на карту", F_M, (255, 255, 255), (SW // 2, 345), True)
        elif self.state == "gameover":
            self.overlay(s, (30, 0, 0, 190))
            text(s, "ИГРА ОКОНЧЕНА", F_XL, (255, 70, 70), (SW // 2, 200), True)
            text(s, "Жизни закончились. Прогресс по карте сохранён.", F_M, (255, 210, 210), (SW // 2, 265), True)
            text(s, "Enter — на карту (жизни вернутся до 3)", F_M, (255, 255, 255), (SW // 2, 330), True)
        elif self.state == "pause":
            self.overlay(s, (0, 0, 0, 130))
            text(s, "ПАУЗА", F_XL, (255, 255, 255), (SW // 2, 210), True)
            text(s, "P — продолжить     Esc (нажать) — выйти на карту", F_M, (230, 230, 230), (SW // 2, 290), True)
        elif self.state == "levelwin":
            self.overlay(s, (0, 0, 40, 130))
            for c in self.confetti:
                D.rect(s, c[2], (c[0], int(c[1]), 8, 5))
            text(s, "Уровень пройден!", F_XL, (255, 230, 100), (SW // 2, 170), True)
            text(s, f"Бонус: +{self.bonus} золота", F_L, (255, 215, 80), (SW // 2, 245), True)
            text(s, f"Золото: {self.prog['gold']}", F_M, (255, 235, 160), (SW // 2, 295), True)
            text(s, "Enter — дальше", F_M, (255, 255, 255), (SW // 2, 350), True)

    def draw_salve(self, s, x, y):
        add_glow(s, x, y, 22, (20, 80, 30))
        D.rect(s, (90, 210, 110), (x - 7, y - 4, 14, 14), border_radius=4)
        D.rect(s, (230, 255, 235), (x - 3, y - 11, 6, 8))
        D.line(s, (255, 255, 255), (x - 3, y + 1), (x + 3, y + 1), 2)
        D.line(s, (255, 255, 255), (x, y - 2), (x, y + 4), 2)

    def draw_player(self, s, cam, oy):
        p = self.p
        if p.inv > 0 and (p.inv // 4) % 2 == 0:
            return
        air = not p.on_ground
        surf = hero_surface(p.hid, p.anim, abs(p.vx) > 0.4, air, self.t, p.cast_t > 0, p.totem > 0)
        sq = p.sq
        if abs(sq - 1) > 0.02:
            surf = t_scale(surf, (110 / sq ** 0.5, 120 * sq))
        if p.facing < 0:
            surf = t_flip(surf, True, False)
        if p.ghost > 0:
            surf = HS(surf.lw, surf.lh, surf=surf.surf.copy())   # копия: спрайты из кэша менять нельзя
            surf.set_alpha(100)
        cx = int(p.cx - cam)
        fy = int(p.y + p.h + oy)
        sh = HSurf((p.w + 14, 10), pygame.SRCALPHA)
        D.ellipse(sh, (0, 0, 0, 80), sh.get_rect())
        s.blit(sh, (cx - sh.get_width() // 2, fy - 5))
        if p.shard:
            add_glow(s, cx, int(p.cy + oy), 62, (20, 70, 100))
        s.blit(surf, (cx - surf.get_width() // 2, fy - (surf.get_height() - 8)))
        if p.shard:
            for k in range(2):
                ang = self.t * 0.08 + k * math.pi
                draw_crystal(s, cx + math.cos(ang) * 30, int(p.cy + oy) + math.sin(ang) * 12 - 10, 6, self.t)
        if p.rot > 0:
            gas = HSurf((int(p.rot_r * 2.2), int(p.rot_r * 2.2)), pygame.SRCALPHA)
            c = gas.get_width() // 2
            D.circle(gas, (110, 200, 80, 55), (c, c), int(p.rot_r))
            D.circle(gas, (140, 230, 100, 110), (c, c), int(p.rot_r), 3)
            s.blit(gas, (cx - c, int(p.cy + oy) - c))

    def draw_tiles(self, s, cam, oy):
        w = self.world
        tl = w.tiles
        x0 = max(0, cam // T)
        x1 = min(w.w, (cam + SW) // T + 2)
        fr = (self.t // 12) % 4
        for ty in range(ROWS):
            for tx in range(x0, x1):
                ch = w.g[ty][tx]
                if ch == " ":
                    continue
                x, y = tx * T - cam, ty * T + oy
                off = 0
                b = self.bumps.get((tx, ty))
                if b:
                    off = -int(math.sin(b / 12 * math.pi) * 8)
                if ch == "#":
                    s.blit(tl["grass"] if not w.solid(tx, ty - 1) else tl["dirt"][(tx * 7 + ty * 13) % 3], (x, y))
                elif ch == "=":
                    s.blit(tl["brick"], (x, y + off))
                elif ch == "?":
                    s.blit(tl["q"][fr], (x, y + off))
                    add_glow(s, x + T // 2, y + T // 2, 36, (50, 36, 6))
                elif ch == "%":
                    s.blit(tl["used"], (x, y + off))
                elif ch == "^":
                    s.blit(tl["spike"], (x, y))

    def draw_hud(self, s):
        p = self.p
        panel(s, (8, 8, 36 + p.maxhp * 27, 74), 130, 12)
        for i in range(p.maxhp):
            draw_heart(s, 18 + i * 27, 14, i < p.hp)
        D.circle(s, (255, 205, 50), (28, 56), 8)
        D.circle(s, (200, 140, 20), (28, 56), 8, 2)
        text(s, str(self.prog["gold"]), F_S, (255, 225, 110), (42, 47))
        text(s, f"x{self.coins}", F_S, (255, 255, 255), (120, 47))
        D.rect(s, (255, 205, 50), (108, 54, 8, 8), border_radius=4)
        text(s, f"♥×{self.lives}", F_S, (255, 120, 140), (170, 47))
        panel(s, (8, 86, 330, 24), 110, 8)
        text(s, f"{p.hero['name']}  ·  {self.world.name}", F_XS, (255, 255, 255), (16, 91), shadow=False)
        for i in range(2):
            x = SW - 192 + i * 94
            name, key, cd = p.hero["ab"][i]
            ready = p.cd[i] <= 0
            panel(s, (x, 8, 86, 56), 150, 10, border=(110, 200, 255, 255) if ready else (90, 90, 110, 255))
            text(s, key, F_L, (255, 255, 255) if ready else (150, 150, 170), (x + 43, 28), True)
            text(s, name, F_XS, (220, 220, 235), (x + 43, 54), True, shadow=False)
            if not ready:
                h = int(56 * p.cd[i] / max(1, p.cdmax[i]))
                o = HSurf((86, h), pygame.SRCALPHA)
                D.rect(o, (0, 0, 0, 150), o.get_rect(), border_radius=8)
                s.blit(o, (x, 8))
        if p.shard:
            panel(s, (SW - 192, 70, 180, 24), 150, 8, border=(110, 220, 255, 255))
            draw_crystal(s, SW - 178, 82, 8, self.t)
            text(s, "Aghanim's Shard", F_XS, (170, 235, 255), (SW - 164, 76), shadow=False)
        if p.totem > 0:
            text(s, "TOTEM!", F_M, (255, 180, 70), (SW // 2, 22), True)
        if p.ghost > 0:
            text(s, "GHOST WALK", F_S, (190, 150, 255), (SW // 2, 22), True)

    # -- меню и карта
    def draw_title(self, s):
        sky = THEMES[0]["sky"]
        s.blit(gradient(sky[0], sky[1]), (0, 0))
        for k in range(7):
            x = (k * 200 - self.t * 0.2) % (SW + 200) - 100
            D.ellipse(s, (255, 255, 255), (x, 120 + (k * 53) % 120, 120, 36))
            D.ellipse(s, (255, 255, 255), (x + 30, 108 + (k * 53) % 120, 80, 36))
        D.polygon(s, (120, 160, 200), [(0, 500), (150, 330), (300, 500)])
        D.polygon(s, (100, 145, 190), [(500, 500), (700, 300), (900, 500)])
        D.rect(s, THEMES[0]["grass"], (0, 500, SW, 40))
        D.rect(s, (60, 130, 50), (0, 500, SW, 5))
        add_glow(s, SW // 2, 60, 260, (60, 50, 10))
        text(s, "DOTA MARIO", F_XL, (255, 220, 90), (SW // 2, 52), True)
        text(s, "Выберите героя  ←  →  и нажмите Enter", F_M, (255, 255, 255), (SW // 2, 100), True)
        cw, gap = 214, 14
        x0 = (SW - (4 * cw + 3 * gap)) // 2
        for i, h in enumerate(HEROES):
            x = x0 + i * (cw + gap)
            sel = i == self.sel
            y = 120 if not sel else 108
            panel(s, (x, y, cw, 382), 225 if sel else 150, 10, col=(20, 25, 45), border=(255, 220, 90, 255) if sel else (120, 130, 160, 255))
            spr = hero_surface(h["id"], self.t * 0.08, False, False, self.t, False, zoom=1.5)
            s.blit(spr, (x + cw // 2 - 82, y + 4))
            text(s, h["name"], F_M, (255, 255, 255), (x + cw // 2, y + 203), True)
            text(s, h["title"], F_S, (200, 210, 240), (x + cw // 2, y + 226), True)
            for k, line in enumerate(h["info"]):
                text(s, line, F_S, (255, 235, 160), (x + 14, y + 248 + k * 20), shadow=False)
            for k, line in enumerate(h["ab_info"]):
                text(s, line, F_XS, (170, 230, 255), (x + 14, y + 316 + k * 18), shadow=False)
            for k, line in enumerate(textwrap.wrap(SHARD_TEXT[h["id"]], 33)[:2]):
                text(s, line, F_XS, (150, 225, 255), (x + 14, y + 348 + k * 15), shadow=False)
        done = len(self.prog["done"])
        text(s, f"Пройдено уровней: {done}/6   Золото: {self.prog['gold']}   Жизни: {self.lives}", F_S, (255, 255, 255), (SW // 2, 514), True)
        text(s, "N — новая игра   M — музыка   Q — свечение   G — графика   F11 — окно / весь экран   Esc (держать 2 сек) — выход", F_XS, (30, 40, 70), (SW // 2, 528), True, shadow=False)

    def draw_map(self, s):
        if self.map_surf is None:
            self.map_surf = make_map_surface()
        s.blit(self.map_surf, (0, 0))
        done = set(self.prog["done"])
        for k in range(5):
            x = (k * 240 - self.t * 0.25) % (SW + 240) - 120
            cl = HSurf((140, 50), pygame.SRCALPHA)
            D.ellipse(cl, (255, 255, 255, 70), (0, 14, 140, 34))
            D.ellipse(cl, (255, 255, 255, 70), (30, 0, 80, 36))
            s.blit(cl, (x, 60 + (k * 97) % 380))
        # фонтан (магазин)
        sx, sy = SHOP_POS
        D.circle(s, (120, 110, 100), (sx, sy), 30)
        D.circle(s, (70, 150, 220), (sx, sy), 24)
        add_glow(s, sx, sy, 40, (20, 60, 90))
        for k in range(5):
            a = self.t * 0.1 + k * 1.26
            D.circle(s, (210, 240, 255), (int(sx + math.cos(a) * 10), int(sy + math.sin(a) * 6 - 6)), 3)
        text(s, "B — магазин", F_XS, (255, 255, 255), (sx, sy + 42), True)
        names = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "R"}
        for n, (x, y) in MAP_NODES.items():
            unl = self.unlocked(n)
            cur = n == self.node and not self.walk
            if n in done:
                col, ring = (255, 205, 60), (255, 245, 170)
            elif unl:
                col, ring = (90, 190, 255), (220, 245, 255)
            else:
                col, ring = (110, 110, 125), (160, 160, 175)
            if n == 6 and unl and n not in done:
                col = (230, 70, 60)
            r = 24 + (3 if cur else 0)
            D.circle(s, (30, 30, 50), (x, y + 3), r + 3)
            D.circle(s, col, (x, y), r)
            D.circle(s, ring, (x, y), r, 3)
            if unl:
                add_glow(s, x, y, 46, tuple(int(c * 0.25) for c in col))
            lab = F_M.render(names[n], True, (20, 20, 40) if unl else (60, 60, 75))
            s.blit(lab, lab.get_rect(center=(x, y)))
            if n in done:
                D.polygon(s, (255, 235, 120), [(x + 18, y - 28), (x + 21, y - 21), (x + 29, y - 21), (x + 23, y - 16), (x + 25, y - 8), (x + 18, y - 13), (x + 11, y - 8), (x + 13, y - 16), (x + 7, y - 21), (x + 15, y - 21)])
            if not unl:
                D.rect(s, (80, 80, 95), (x - 7, y - 4, 14, 11), border_radius=2)
                D.arc(s, (80, 80, 95), (x - 6, y - 12, 12, 14), 0, math.pi, 3)
        # герой на дороге
        if self.walk:
            a, b, t = self.walk
            px, py = edge_point(a, b, t)
        else:
            px, py = MAP_NODES[self.node]
        spr = hero_surface(HEROES[self.sel]["id"], self.t * 0.2, bool(self.walk), False, self.t, False, zoom=0.6)
        bob = math.sin(self.t * 0.15) * 2 if not self.walk else abs(math.sin(self.t * 0.3)) * -4
        s.blit(spr, (px - 33, py - 66 + bob))
        # панель информации
        info = LEVELS[self.node - 1]
        panel(s, (SW // 2 - 300, SH - 92, 600, 80), 190, 14, border=(255, 220, 90, 255))
        status = "пройден" if self.node in done else ("можно играть" if self.unlocked(self.node) else "закрыт")
        text(s, f"{self.node}. {info['name']}", F_M, (255, 255, 255), (SW // 2, SH - 70), True)
        for i in range(5):
            draw_star(s, SW // 2 - 96 + i * 20, SH - 44, 8, i < info["stars"])
        text(s, f"сложность   ·   {status}", F_S, (255, 225, 110), (SW // 2 + 130, SH - 44), True)
        text(s, "Стрелки — по дороге   Enter — играть   B — магазин   Tab — сменить героя   Esc — меню", F_XS, (200, 210, 235), (SW // 2, SH - 24), True, shadow=False)
        panel(s, (8, 8, 330, 30), 150, 10)
        text(s, f"{HEROES[self.sel]['name']}    золото {self.prog['gold']}    жизни {self.lives}", F_S, (255, 235, 160), (18, 12), shadow=False)
        if self.prog.get("shard"):
            draw_crystal(s, 358, 24, 9, self.t)
            text(s, "шард готов", F_XS, (170, 235, 255), (372, 16), shadow=False)

    def draw_shop(self, s):
        self.overlay(s, (0, 0, 20, 150))
        panel(s, (SW // 2 - 340, 70, 680, 400), 235, 16, border=(255, 220, 90, 255))
        text(s, "МАГАЗИН", F_L, (255, 220, 90), (SW // 2, 110), True)
        text(s, f"Золото: {self.prog['gold']}", F_M, (255, 235, 160), (SW // 2, 154), True)
        for i, (k, name, desc, price, mx) in enumerate(SHOP):
            y = 190 + i * 52
            sel = i == self.shop_sel
            if sel:
                D.rect(s, (60, 70, 110), (SW // 2 - 320, y - 4, 640, 48), border_radius=10)
            lvl = self.shop_level(k)
            maxed = lvl >= mx if k != "life" else lvl >= 9
            cost = self.shop_price(k)
            can = self.prog["gold"] >= cost and not maxed
            text(s, name, F_M, (255, 255, 255) if sel else (200, 205, 225), (SW // 2 - 304, y), shadow=False)
            text(s, desc, F_XS, (170, 180, 210), (SW // 2 - 304, y + 26), shadow=False)
            if k in ("boots", "vit", "cd"):
                label = f"ур. {lvl}/{mx}"
            elif k == "shard":
                label = "готов" if lvl else ""
            else:
                label = f"жизней: {lvl}"
            text(s, label, F_S, (255, 235, 160), (SW // 2 + 130, y + 8), shadow=False)
            text(s, "МАКС" if maxed else f"{cost}", F_M, (120, 255, 140) if can else (255, 110, 110), (SW // 2 + 300, y + 8), True)
        text(s, "↑ ↓ — выбор    Enter — купить    Esc / B — назад", F_S, (200, 210, 235), (SW // 2, 446), True, shadow=False)

    def draw_ending(self, s):
        sky = THEMES[0]["sky"]
        s.blit(gradient(sky[0], sky[1]), (0, 0))
        for c in self.confetti:
            D.rect(s, c[2], (c[0], int(c[1]), 8, 5))
        spr = hero_surface(HEROES[self.sel]["id"], self.t * 0.08, False, False, self.t, False, zoom=2.0)
        s.blit(spr, (SW // 2 - 110, 250))
        text(s, "ПОБЕДА!", F_XL, (255, 230, 100), (SW // 2, 90), True)
        text(s, "Все уровни пройдены, Рошан повержен", F_M, (255, 255, 255), (SW // 2, 160), True)
        text(s, f"Золото: {self.prog['gold']}", F_L, (255, 215, 80), (SW // 2, 205), True)
        text(s, "Enter — в меню", F_M, (255, 255, 255), (SW // 2, 505), True)


KEYMAP_HELD = {
    pygame.K_LEFT: "left", pygame.K_a: "left", pygame.K_RIGHT: "right", pygame.K_d: "right",
    pygame.K_UP: "jump", pygame.K_w: "jump", pygame.K_SPACE: "jump",
}
KEYMAP_PRESS = {
    pygame.K_LEFT: ["left"], pygame.K_a: ["left"], pygame.K_RIGHT: ["right"], pygame.K_d: ["right"],
    pygame.K_UP: ["jump", "up"], pygame.K_w: ["jump", "up"], pygame.K_SPACE: ["jump"], pygame.K_DOWN: ["down"],
    pygame.K_s: ["down"], pygame.K_j: ["a1"], pygame.K_x: ["a1"], pygame.K_k: ["a2"], pygame.K_c: ["a2"],
    pygame.K_RETURN: ["enter"], pygame.K_KP_ENTER: ["enter"], pygame.K_p: ["pause"],
    pygame.K_r: ["restart"], pygame.K_b: ["shop"], pygame.K_TAB: ["hero"],
    pygame.K_h: ["hero"], pygame.K_n: ["new"], pygame.K_m: ["mute"], pygame.K_q: ["quality"], pygame.K_g: ["gfx"],
}
# Esc обрабатывается отдельно: короткое нажатие = "назад", удержание 2 секунды = выход.
ESC_TAP = 0.4      # короче этого - обычное нажатие
ESC_QUIT = 2.0     # столько секунд держать Esc для выхода


def load_settings():
    d = {"fullscreen": False, "bloom": True, "win": None}
    try:
        with open(os.path.join(save_dir(), "settings.json"), encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def save_settings(d):
    try:
        with open(os.path.join(save_dir(), "settings.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


QUALITY = [("Обычная", 1.0), ("Высокая", 1.5), ("Максимальная", 2.0)]
DEFAULT_QUALITY = 2


class Display:
    """Окно или полный экран. Картинка рисуется в 960x540 и плавно масштабируется под любой размер."""

    def __init__(self, settings):
        self.st = settings
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = 1920, 1080
        w = int(min(1280, dw * 0.92))
        h = w * 9 // 16
        if h > dh * 0.86:
            h = int(dh * 0.86)
            w = h * 16 // 9
        win = settings.get("win")
        self.win_size = (max(480, int(win[0])), max(270, int(win[1]))) if win else (w, h)
        self.full = bool(settings.get("fullscreen"))
        self.canvas = None
        self.scaled = None
        self.last = None
        self.quality = settings.get("quality", DEFAULT_QUALITY)
        self.apply()
        self.set_quality(self.quality)

    def apply(self):
        try:
            if self.full:
                pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                pygame.display.set_mode(self.win_size, pygame.RESIZABLE)
        except Exception:
            self.full = False
            pygame.display.set_mode((SW, SH))
        pygame.mouse.set_visible(not self.full)
        if self.canvas is None:
            self.canvas = HS(SW, SH)
        self.scaled = None
        self.last = None

    def set_quality(self, idx):
        """Меняет разрешение рендера (1x / 1.5x / 2x) и пересоздаёт холст."""
        idx = max(0, min(len(QUALITY) - 1, idx))
        self.quality = idx
        set_scale(QUALITY[idx][1])
        self.canvas = HS(SW, SH)
        self.scaled = None
        self.st["quality"] = idx
        return idx

    def toggle(self):
        if not self.full:
            self.win_size = pygame.display.get_surface().get_size()
        self.full = not self.full
        self.apply()
        self.remember()

    def remember(self):
        if not self.full:
            self.win_size = pygame.display.get_surface().get_size()
        self.st["fullscreen"] = self.full
        self.st["win"] = list(self.win_size)
        save_settings(self.st)

    def present(self):
        win = pygame.display.get_surface()
        w, h = win.get_size()
        src = self.canvas.surf
        cw, ch = src.get_size()
        k = min(w / cw, h / ch)
        tw, th = max(1, int(cw * k)), max(1, int(ch * k))
        if self.last != (w, h):
            win.fill((0, 0, 0))
            self.last = (w, h)
            self.scaled = None
        if (tw, th) == (cw, ch):
            win.blit(src, ((w - tw) // 2, (h - th) // 2))
        else:
            # уменьшение кадра из высокого разрешения даёт сглаживание краёв
            if self.scaled is None or self.scaled.get_size() != (tw, th):
                self.scaled = pygame.Surface((tw, th)).convert()
            pygame.transform.smoothscale(src, (tw, th), self.scaled)
            win.blit(self.scaled, ((w - tw) // 2, (h - th) // 2))
        pygame.display.flip()


def change_quality(disp, game, idx, auto_note=False):
    idx = disp.set_quality(idx)
    game.rebuild_gfx()
    name = QUALITY[idx][0]
    game.flash_msg(("Авто: графика снижена до «%s»" if auto_note else "Графика: %s") % name)
    if not auto_note:
        save_settings(disp.st)


def main():
    init_sounds()
    settings = load_settings()
    disp = Display(settings)
    clock = pygame.time.Clock()
    game = Game(settings)
    inp = Input()
    esc_t0 = None
    auto = {"on": not settings.get("q_manual"), "acc": 0, "n": 0, "bad": 0}   # авто-режим, пока игрок не выбрал сам

    def quit_game():
        game.save()
        disp.remember()
        save_settings(settings)
        pygame.quit()
        sys.exit()

    while True:
        inp.pressed = set()
        now = pygame.time.get_ticks() / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                quit_game()
            if ev.type == pygame.WINDOWFOCUSLOST:
                esc_t0 = None
                game.exit_p = 0
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11 or (ev.key == pygame.K_RETURN and ev.mod & pygame.KMOD_ALT):
                    disp.toggle()
                    continue
                if ev.key == pygame.K_ESCAPE:
                    if esc_t0 is None:
                        esc_t0 = now
                    continue
                for name in KEYMAP_PRESS.get(ev.key, ()):
                    inp.pressed.add(name)
            elif ev.type == pygame.KEYUP and ev.key == pygame.K_ESCAPE:
                if esc_t0 is not None and now - esc_t0 < ESC_TAP:
                    inp.pressed.add("back")
                esc_t0 = None
                game.exit_p = 0
        if esc_t0 is not None:
            held_for = now - esc_t0
            game.exit_p = max(0.0, min(1.0, (held_for - ESC_TAP) / (ESC_QUIT - ESC_TAP)))
            if held_for >= ESC_QUIT:
                quit_game()
        keys = pygame.key.get_pressed()
        inp.held = {v for k, v in KEYMAP_HELD.items() if keys[k]}
        if "gfx" in inp.pressed:
            settings["q_manual"] = True
            auto["on"] = False
            change_quality(disp, game, (disp.quality + 1) % len(QUALITY))
        game.update(inp)
        game.draw(disp.canvas)
        disp.present()
        dt = clock.tick(FPS)
        # автоматически снижаем разрешение, если игра идёт рывками
        if auto["on"] and disp.quality > 0:
            auto["acc"] += dt
            auto["n"] += 1
            if auto["n"] >= 150:
                avg = auto["acc"] / auto["n"]
                auto["acc"], auto["n"] = 0, 0
                if avg > 24:
                    auto["bad"] += 1
                else:
                    auto["bad"] = 0
                if auto["bad"] >= 2:
                    auto["bad"] = 0
                    change_quality(disp, game, disp.quality - 1, auto_note=True)


if __name__ == "__main__":
    main()
