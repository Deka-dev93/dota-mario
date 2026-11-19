"""Синтезатор музыки для Dota Mario. Запуск:  py make_music.py
Создаёт в папке music/ три оригинальных трека (WAV, зацикленные):
  level.wav - замедленный фонк (808, кубелл, реверб) для уровней,
  map.wav   - спокойный эмбиент для карты мира и меню,
  boss.wav  - тяжёлый трек для битвы с Рошаном.
Это оригинальная музыка, написанная кодом в похожем настроении. Чтобы поставить свой трек,
положите файл music/level.mp3 (или .ogg) - игра предпочтёт его.
"""
import math
import os
import random
import struct
import wave

SR = 22050
rnd = random.Random(42)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


class Track:
    def __init__(self, bpm, bars, tail=3.0):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.n = int(SR * self.beat * 4 * bars)
        self.tail = int(SR * tail)
        self.buf = [0.0] * (self.n + self.tail)

    def t(self, bar, beat):
        return int(SR * self.beat * (bar * 4 + beat))

    def add(self, start, samples, gain=1.0):
        b = self.buf
        end = min(len(b), start + len(samples))
        for i in range(start, end):
            b[i] += samples[i - start] * gain

    def fold(self):
        b = self.buf
        for i in range(self.tail):
            b[i] += b[self.n + i]
        return b[: self.n]


def kick(dur=0.38, f0=160, f1=42):
    n = int(SR * dur)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / SR
        f = f1 + (f0 - f1) * math.exp(-t * 28)
        ph += 2 * math.pi * f / SR
        out.append(math.sin(ph) * math.exp(-t * 8.0) * min(1, i / 40))
    return out


def bass808(freq, dur, drive=2.2):
    n = int(SR * dur)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / SR
        f = freq * (1 + 0.6 * math.exp(-t * 60))
        ph += 2 * math.pi * f / SR
        env = min(1, i / 80) * math.exp(-t * 1.5) * (1 - 0.0 * t)
        out.append(math.tanh(math.sin(ph) * drive) * env * 0.8)
    for i in range(min(300, n)):
        out[n - 1 - i] *= i / 300
    return out


def snare(dur=0.28):
    n = int(SR * dur)
    out = []
    prev = 0.0
    ph = 0.0
    for i in range(n):
        t = i / SR
        x = rnd.uniform(-1, 1)
        hp = x - prev * 0.6
        prev = x
        ph += 2 * math.pi * 190 / SR
        out.append((hp * math.exp(-t * 22) * 0.9 + math.sin(ph) * math.exp(-t * 30) * 0.5))
    return out


def clap(dur=0.3):
    n = int(SR * dur)
    out = []
    prev = 0.0
    for i in range(n):
        t = i / SR
        x = rnd.uniform(-1, 1)
        hp = x - prev * 0.5
        prev = x
        env = math.exp(-t * 16)
        for k in (0.0, 0.012, 0.026):
            if t >= k:
                env += 0.5 * math.exp(-(t - k) * 60)
        out.append(hp * env * 0.5)
    return out


def hat(dur=0.08, open_=False):
    n = int(SR * (0.3 if open_ else dur))
    out = []
    prev = 0.0
    k = 14 if open_ else 80
    for i in range(n):
        t = i / SR
        x = rnd.uniform(-1, 1)
        hp = x - prev
        prev = x
        out.append(hp * math.exp(-t * k) * 0.35)
    return out


def cowbell(freq, dur=0.3):
    n = int(SR * dur)
    out = []
    f2 = freq * 1.504
    for i in range(n):
        t = i / SR
        a = 1 if math.sin(2 * math.pi * freq * t) > 0 else -1
        b = 1 if math.sin(2 * math.pi * f2 * t) > 0 else -1
        out.append((a * 0.5 + b * 0.5) * math.exp(-t * 11) * 0.35 * min(1, i / 30))
    # мягкий фильтр низких, чтобы звучало "приглушённо"
    y = 0.0
    for i in range(n):
        y += (out[i] - y) * 0.35
        out[i] = y
    return out


def bell(freq, dur=1.2):
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        v = (math.sin(2 * math.pi * freq * t) + 0.4 * math.sin(2 * math.pi * freq * 2.76 * t) * math.exp(-t * 4)
             + 0.25 * math.sin(2 * math.pi * freq * 5.4 * t) * math.exp(-t * 8))
        out.append(v * math.exp(-t * 2.6) * 0.3 * min(1, i / 50))
    return out


def pad(freqs, dur, lp=0.06, trem=0.25, gain=0.12):
    n = int(SR * dur)
    out = [0.0] * n
    y = 0.0
    dets = (0.994, 1.0, 1.006)
    for i in range(n):
        t = i / SR
        s = 0.0
        for f in freqs:
            for d in dets:
                ph = (t * f * d) % 1.0
                s += (ph * 2 - 1)
        s /= len(freqs) * len(dets)
        a = min(1, t / 0.9) * min(1, (dur - t) / 0.9) * (0.8 + 0.2 * math.sin(2 * math.pi * trem * t))
        y += (s - y) * lp
        out[i] = y * a * gain * 4
    return out


def reverb(buf, wet=0.38, size=1.0):
    combs = [int(d * size) for d in (1557, 1617, 1491, 1422, 1277, 1356)]
    gains = [0.84, 0.83, 0.82, 0.81, 0.80, 0.79]
    n = len(buf)
    acc = [0.0] * n
    for d, g in zip(combs, gains):
        line = [0.0] * d
        idx = 0
        for i in range(n):
            x = buf[i]
            y = line[idx]
            line[idx] = x + y * g
            idx += 1
            if idx == d:
                idx = 0
            acc[i] += y
    # два all-pass
    for d in (225, 556):
        line = [0.0] * d
        idx = 0
        for i in range(n):
            x = acc[i]
            y = line[idx]
            line[idx] = x + y * 0.5
            acc[i] = y - x * 0.5 + 0.0
            idx += 1
            if idx == d:
                idx = 0
    # фильтр высоких на хвосте реверба (звук "из-под воды")
    lp = 0.0
    for i in range(n):
        lp += (acc[i] - lp) * 0.25
        acc[i] = lp
    return [buf[i] * (1 - wet * 0.5) + acc[i] * wet * 0.28 for i in range(n)]


def master(buf, lp=0.55):
    y = 0.0
    out = []
    for x in buf:
        y += (x - y) * lp
        out.append(y)
    peak = max(1e-6, max(abs(v) for v in out))
    return [math.tanh(v / peak * 1.25) * 0.8 for v in out]


def write(path, buf):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in buf))


# ---------- ТРЕК 1: замедленный фонк для уровней (ре минор) ----------
def make_level():
    tr = Track(bpm=70, bars=8)
    roots = [38, 38, 34, 34, 36, 36, 33, 38]  # D, D, Bb, Bb, C, C, A, D
    chords = [[62, 65, 69], [62, 65, 69], [58, 62, 65], [58, 62, 65], [60, 64, 67], [60, 64, 67], [57, 61, 64], [62, 65, 69]]
    k, sn, cl = kick(), snare(), clap()
    h, ho = hat(), hat(open_=True)
    for bar in range(8):
        tr.add(tr.t(bar, 0), kick(), 0.9)
        tr.add(tr.t(bar, 2.5), k, 0.7)
        if bar % 2 == 1:
            tr.add(tr.t(bar, 3.75), k, 0.6)
        tr.add(tr.t(bar, 1), sn, 0.55)
        tr.add(tr.t(bar, 1), cl, 0.7)
        tr.add(tr.t(bar, 3), sn, 0.55)
        tr.add(tr.t(bar, 3), cl, 0.7)
        for i in range(8):
            tr.add(tr.t(bar, i * 0.5), h, 0.5 if i % 2 == 0 else 0.3)
        if bar % 4 == 3:
            for i in range(8):
                tr.add(tr.t(bar, 3 + i * 0.125), h, 0.45)
        tr.add(tr.t(bar, 3.5), ho, 0.45)
        # 808
        f = midi(roots[bar])
        tr.add(tr.t(bar, 0), bass808(f, tr.beat * 2.4), 0.95)
        tr.add(tr.t(bar, 2.5), bass808(f * (1.5 if bar % 2 else 1.0), tr.beat * 1.3), 0.8)
        # пад
        tr.add(tr.t(bar, 0), pad([midi(n) for n in chords[bar]], tr.beat * 4.2), 0.9)
    # кубелл-мелодия (классическая "фонк" фраза), 2 такта, повтор с вариацией
    motif_a = [(0, 74), (0.75, 74), (1.5, 77), (2.5, 74), (3.25, 72)]
    motif_b = [(0, 72), (0.75, 72), (1.5, 74), (2.5, 69), (3.25, 70)]
    for bar in range(0, 8, 2):
        for m, notes in enumerate((motif_a, motif_b)):
            for beat, n in notes:
                tr.add(tr.t(bar + m, beat), cowbell(midi(n)), 0.8 if bar < 4 else 0.95)
    return master(reverb(tr.fold(), wet=0.9, size=1.25))


# ---------- ТРЕК 2: эмбиент для карты мира ----------
def make_map():
    tr = Track(bpm=60, bars=8, tail=4.0)
    chords = [[50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64], [45, 52, 57, 61]] * 2
    arp = [74, 77, 81, 77, 74, 69, 72, 77]
    for bar in range(8):
        tr.add(tr.t(bar, 0), pad([midi(n) for n in chords[bar]], tr.beat * 4.4, lp=0.05, gain=0.16), 1.0)
        tr.add(tr.t(bar, 0), bass808(midi(chords[bar][0] - 12), tr.beat * 3.5, drive=1.2), 0.5)
        for i in range(8):
            if (bar + i) % 3 != 2:
                tr.add(tr.t(bar, i * 0.5), bell(midi(arp[(i + bar) % 8] + (12 if bar % 4 == 3 else 0))), 0.45)
        if bar % 2 == 0:
            tr.add(tr.t(bar, 0), kick(dur=0.5, f0=120, f1=45), 0.5)
    return master(reverb(tr.fold(), wet=1.0, size=1.5))


# ---------- ТРЕК 3: босс ----------
def make_boss():
    tr = Track(bpm=88, bars=8, tail=2.5)
    roots = [38, 38, 41, 38, 38, 38, 36, 37]  # D D F D D D C Db
    k, sn = kick(), snare()
    h = hat()
    for bar in range(8):
        for b in (0, 1, 2, 3):
            tr.add(tr.t(bar, b), k, 0.9)
        tr.add(tr.t(bar, 1.5), k, 0.6)
        tr.add(tr.t(bar, 1), sn, 0.7)
        tr.add(tr.t(bar, 3), sn, 0.7)
        for i in range(16):
            tr.add(tr.t(bar, i * 0.25), h, 0.45 if i % 4 else 0.6)
        f = midi(roots[bar])
        for i, off in enumerate((0, 0.75, 1.5, 2.25, 3)):
            tr.add(tr.t(bar, off), bass808(f * (1 if i % 2 == 0 else 1.122), tr.beat * 0.9, drive=3.5), 0.8)
        tr.add(tr.t(bar, 0), pad([midi(roots[bar] + 24), midi(roots[bar] + 27), midi(roots[bar] + 30)], tr.beat * 4.2, lp=0.04, gain=0.1), 0.9)
    lead = [(0, 74), (0.5, 74), (1, 77), (1.5, 74), (2, 73), (3, 70)]
    for bar in range(8):
        for beat, n in lead:
            tr.add(tr.t(bar, beat), cowbell(midi(n + (12 if bar >= 4 else 0)), 0.22), 0.8)
    return master(reverb(tr.fold(), wet=0.7, size=1.0))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
    os.makedirs(out, exist_ok=True)
    for name, fn in (("level", make_level), ("map", make_map), ("boss", make_boss)):
        print("синтез", name, "...", flush=True)
        write(os.path.join(out, name + ".wav"), fn())
        print("готово", name, flush=True)
