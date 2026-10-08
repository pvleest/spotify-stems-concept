#!/usr/bin/env python3
"""Render original, sample-aligned stems for the Glass Garden demo.

Key: A minor. Tempo: 112 BPM. 32 bars + reverb tail.
No third-party recordings. Numpy only.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

SR = 44100
BPM = 112
BARS = 32
BEAT = 60.0 / BPM
BAR = 4.0 * BEAT
SONG = BARS * BAR
TAIL = 2.0
TOTAL = SONG + TAIL
N = int(round(TOTAL * SR))
RNG = np.random.default_rng(20261008)

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "audio"

# bar % 4 -> chord, except the final two bars resolve to Am
CHORD_OF = {0: "Am", 1: "F", 2: "C", 3: "G"}
BASS_ROOT = {"Am": 45, "F": 41, "C": 48, "G": 43}  # A2 F2 C3 G2
# guitar voicings
GUITAR = {
    "Am": (57, 60, 64),
    "F": (53, 57, 60),
    "C": (55, 60, 64),
    "G": (55, 59, 62),
}
# pad voicings
PAD = {
    "Am": (57, 64, 69, 72),
    "F": (53, 60, 65, 69),
    "C": (52, 60, 64, 67),
    "G": (55, 62, 67, 71),
}


def midi_hz(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def style_of(bar: int) -> str:
    if bar < 4:
        return "intro"
    if bar < 12:
        return "verse"
    if bar < 20:
        return "chorus"
    if bar < 24:
        return "break"
    return "chorus"


def chord_of(bar: int) -> str:
    if bar >= 30:
        return "Am"
    return CHORD_OF[bar % 4]


def env_asr(n: int, attack: float, release: float, sr: int = SR) -> np.ndarray:
    e = np.ones(n, dtype=np.float64)
    a = min(n, int(attack * sr))
    r = min(n - a, int(release * sr))
    if a > 1:
        e[:a] = np.linspace(0.0, 1.0, a)
    if r > 1:
        e[-r:] *= np.linspace(1.0, 0.0, r)
    return e


def fir_lp(cutoff: float, taps: int = 95) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.sin(2 * np.pi * cutoff / SR * n) / (np.pi * n)
    h[(taps - 1) // 2] = 2 * cutoff / SR
    h *= np.hamming(taps)
    s = h.sum()
    if s != 0:
        h /= s
    return h


def lowpass(x: np.ndarray, cutoff: float, taps: int = 95) -> np.ndarray:
    return np.convolve(x, fir_lp(cutoff, taps), mode="same")


def highpass(x: np.ndarray, cutoff: float, taps: int = 95) -> np.ndarray:
    return x - lowpass(x, cutoff, taps)


def fft_conv(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = 1
    need = len(x) + len(ir) - 1
    while n < need:
        n *= 2
    y = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)
    return y[: len(x)]


def make_ir(seconds: float = 0.85, decay: float = 3.4) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    noise = RNG.normal(0, 1, n)
    noise = lowpass(noise, 6500, 63)
    ir = noise * np.exp(-decay * t)
    for delay, gain in ((0.013, 0.55), (0.027, 0.34), (0.041, 0.22), (0.067, 0.14), (0.091, 0.08)):
        i = int(delay * SR)
        if i < n:
            ir[i] += gain * 2.5
    ir = lowpass(ir, 5000, 63)
    ir[0] = 0.0
    peak = np.max(np.abs(ir)) or 1.0
    return ir / peak


IR = None


def reverb(x: np.ndarray, wet: float) -> np.ndarray:
    if wet <= 0:
        return x
    global IR
    if IR is None:
        IR = make_ir()
    wet_sig = fft_conv(x, IR)
    # keep the dry peak relationship: wet is a send
    peak = np.max(np.abs(wet_sig)) or 1.0
    wet_sig = wet_sig / peak
    dry_peak = np.max(np.abs(x)) or 1.0
    return x + wet_sig * dry_peak * wet


def mix_in(dst: np.ndarray, src: np.ndarray, start: int, gain: float = 1.0) -> None:
    if gain == 0 or len(src) == 0:
        return
    i = int(start)
    if i < 0:
        src = src[-i:]
        i = 0
    if i >= len(dst):
        return
    n = min(len(src), len(dst) - i)
    dst[i : i + n] += src[:n] * gain


def additive(freq: float, n: int, harmonics: list[tuple[float, float]], vib: float = 0.0, vib_rate: float = 5.2) -> np.ndarray:
    t = np.arange(n) / SR
    if vib:
        inst = freq * (1.0 + vib * np.sin(2 * np.pi * vib_rate * t))
    else:
        inst = np.full(n, freq)
    phase = 2 * np.pi * np.cumsum(inst) / SR
    y = np.zeros(n, dtype=np.float64)
    for k, amp in harmonics:
        y += amp * np.sin(k * phase)
    return y


# ---------- drums ----------
def make_kick() -> np.ndarray:
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 145 * np.exp(-t * 26)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t * 6.2)
    punch = np.sin(2 * np.pi * 175 * t) * np.exp(-t * 38)
    click_n = int(0.012 * SR)
    click = np.sin(2 * np.pi * 2400 * t[:click_n]) * np.linspace(1, 0, click_n) ** 2
    y = body * 0.95 + punch * 0.28
    y[:click_n] += click * 0.18
    y *= env_asr(n, 0.001, 0.02)
    return np.tanh(y * 1.25)


def make_snare() -> np.ndarray:
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 188 * t) * np.exp(-t * 16) * 0.55
    tone += np.sin(2 * np.pi * 318 * t) * np.exp(-t * 22) * 0.22
    noise = RNG.normal(0, 1, n)
    noise = highpass(noise, 700, 63)
    noise *= np.exp(-t * 13.5)
    y = tone + noise * 0.72
    y *= env_asr(n, 0.001, 0.03)
    return np.tanh(y * 1.15)


def make_clap() -> np.ndarray:
    n = int(0.22 * SR)
    y = np.zeros(n)
    for delay, amp in ((0.0, 1.0), (0.011, 0.75), (0.021, 0.45), (0.034, 0.22)):
        i = int(delay * SR)
        m = n - i
        tt = np.arange(m) / SR
        burst = RNG.normal(0, 1, m) * np.exp(-tt * 26)
        y[i:] += amp * burst
    y = highpass(y, 850, 63)
    y = lowpass(y, 6500, 63)
    peak = np.max(np.abs(y)) or 1.0
    return y / peak * 0.85


def make_hat(open_hat: bool = False) -> np.ndarray:
    dur = 0.16 if open_hat else 0.045
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = RNG.normal(0, 1, n)
    noise = highpass(noise, 6200, 63)
    decay = 12 if open_hat else 58
    y = noise * np.exp(-t * decay)
    # metallic partials
    y += 0.25 * np.sin(2 * np.pi * 7200 * t) * np.exp(-t * (decay * 0.8))
    y += 0.18 * np.sin(2 * np.pi * 10400 * t) * np.exp(-t * decay)
    peak = np.max(np.abs(y)) or 1.0
    return y / peak


def make_crash() -> np.ndarray:
    n = int(1.35 * SR)
    t = np.arange(n) / SR
    noise = highpass(RNG.normal(0, 1, n), 4500, 63)
    y = noise * np.exp(-t * 2.6)
    y += 0.2 * np.sin(2 * np.pi * 5400 * t) * np.exp(-t * 3.2)
    peak = np.max(np.abs(y)) or 1.0
    return y / peak * 0.7


def make_riser() -> np.ndarray:
    n = int(BEAT * SR)
    t = np.arange(n) / SR
    noise = highpass(RNG.normal(0, 1, n), 1800, 63)
    env = np.linspace(0, 1, n) ** 2
    return noise * env * 0.45


def render_drums() -> np.ndarray:
    kick = make_kick()
    snare = make_snare()
    clap = make_clap()
    hat = make_hat(False)
    ohat = make_hat(True)
    crash = make_crash()
    riser = make_riser()
    dry = np.zeros(N)
    send = np.zeros(N)
    for bar in range(BARS):
        st = style_of(bar)
        base = int(round(bar * BAR * SR))
        step = BAR / 16.0
        def at(sixteenth: float) -> int:
            human = 0.0
            if sixteenth not in (0, 4, 8, 12):
                human = float(RNG.uniform(-0.004, 0.006))
            return base + int(round((sixteenth * step + human) * SR))

        if st == "intro":
            for s in (0, 8):
                mix_in(dry, kick, at(s), 0.62)
            for s in (0, 2, 4, 6, 8, 10, 12, 14):
                mix_in(dry, hat, at(s), 0.18)
        elif st == "verse":
            for s, g in ((0, 0.95), (6, 0.55), (8, 0.9), (14, 0.48)):
                mix_in(dry, kick, at(s), g)
            mix_in(dry, snare, at(4), 0.85)
            mix_in(send, snare, at(4), 0.85)
            mix_in(dry, snare, at(12), 0.9)
            mix_in(send, snare, at(12), 0.9)
            for s in (0, 2, 4, 6, 8, 10, 12, 14):
                mix_in(dry, hat, at(s), 0.28 if s % 4 == 0 else 0.18)
            if bar % 2 == 0:
                mix_in(dry, ohat, at(10), 0.22)
                mix_in(send, ohat, at(10), 0.22)
        elif st == "break":
            mix_in(dry, kick, at(0), 0.7)
            mix_in(dry, kick, at(8), 0.55)
            mix_in(dry, snare, at(12), 0.55)
            mix_in(send, snare, at(12), 0.55)
            for s in (0, 4, 8, 12):
                mix_in(dry, hat, at(s), 0.14)
        else:
            # chorus
            for s, g in ((0, 1.0), (4, 0.72), (8, 0.95), (12, 0.72)):
                mix_in(dry, kick, at(s), g)
            if bar % 2 == 1:
                mix_in(dry, kick, at(14), 0.4)
            for s in (4, 12):
                mix_in(dry, snare, at(s), 0.95)
                mix_in(send, snare, at(s), 0.95)
                mix_in(dry, clap, at(s), 0.42)
                mix_in(send, clap, at(s), 0.42)
            # ghost
            mix_in(dry, snare, at(11), 0.16)
            for s in range(16):
                accent = 0.34 if s % 2 == 0 else 0.16
                if s % 4 == 0:
                    accent = 0.4
                mix_in(dry, hat, at(s), accent)
            if bar in (12, 24):
                mix_in(dry, crash, at(0), 0.55)
                mix_in(send, crash, at(0), 0.7)
            if bar in (11, 23):
                mix_in(dry, riser, at(12), 0.35)

    if True:
        # last-bar fill, light
        bar = 31
        base = int(round(bar * BAR * SR))
        step = BAR / 16.0
        for s, g in ((8, 0.25), (10, 0.32), (12, 0.45), (14, 0.6)):
            mix_in(dry, snare, base + int(round(s * step * SR)), g)

    bus = np.tanh(dry * 1.15)
    bus = bus + reverb(send, 0.22) * 0.9
    return bus


# ---------- pitched notes ----------
def render_bass() -> np.ndarray:
    y = np.zeros(N)
    for bar in range(BARS):
        st = style_of(bar)
        if st == "intro" and bar < 2:
            continue
        root = BASS_ROOT[chord_of(bar)]
        fifth = root + 7
        if st == "intro":
            events = [(0.0, 3.4, root, 0.62)]
        elif st == "break":
            events = [(0.0, 3.3, root, 0.75)]
        elif st == "verse":
            events = [
                (0.0, 1.35, root, 0.92),
                (2.0, 0.7, fifth, 0.62),
                (3.0, 0.85, root, 0.78),
            ]
        else:
            events = [
                (0.0, 0.42, root - 12, 1.0),
                (0.5, 0.38, root, 0.72),
                (1.0, 0.38, root, 0.68),
                (1.5, 0.38, fifth, 0.7),
                (2.0, 0.42, root, 0.9),
                (2.5, 0.36, root + 12, 0.48),
                (3.0, 0.38, fifth, 0.66),
                (3.5, 0.32, root, 0.6),
            ]
        for beat, dur, midi, vel in events:
            n = int(dur * BEAT * SR)
            if n < 8:
                continue
            freq = midi_hz(midi)
            t = np.arange(n) / SR
            glide = freq * (1.0 - (0.05 if st == "chorus" else 0.0) * np.exp(-t * 36))
            phase = 2 * np.pi * np.cumsum(glide) / SR
            sig = (
                np.sin(phase) * 0.72
                + np.sin(2 * phase) * 0.48
                + np.sin(3 * phase) * 0.16
                + np.sin(4 * phase) * 0.06
            )
            e = env_asr(n, 0.006, 0.05)
            # slight decay so eighths don't mush
            e *= np.exp(-t * (2.2 if st == "chorus" else 1.1))
            e = np.maximum(e, 0)
            # renormalize attack
            sig = sig * e * vel
            start = int(round((bar * BAR + beat * BEAT) * SR))
            mix_in(y, sig, start, 1.0)
    y = lowpass(y, 2800, 63)
    y = reverb(y, 0.08)
    return y


def render_keys() -> np.ndarray:
    y = np.zeros(N)
    for bar in range(BARS):
        st = style_of(bar)
        tones = PAD[chord_of(bar)]
        dur = BAR + 0.12
        n = int(dur * SR)
        t = np.arange(n) / SR
        sig = np.zeros(n)
        section = {"intro": 0.5, "verse": 0.78, "chorus": 1.0, "break": 0.62}[st]
        for idx, midi in enumerate(tones):
            base = midi_hz(midi)
            for cents, amp in ((-7, 0.34), (0, 0.42), (8, 0.32)):
                freq = base * (2 ** (cents / 1200))
                phase = 2 * np.pi * freq * t
                sig += amp * np.sin(phase)
                if st == "chorus":
                    sig += amp * 0.22 * np.sin(2 * phase)
            # very quiet fifth shimmer on top voice
            if idx == len(tones) - 1 and st != "intro":
                sig += 0.08 * np.sin(2 * np.pi * base * t)
        lfo = 0.9 + 0.1 * np.sin(2 * np.pi * 0.13 * t + bar)
        e = env_asr(n, 0.09 if st != "chorus" else 0.05, 0.16)
        sig = sig * e * lfo * section
        start = int(round(bar * BAR * SR))
        mix_in(y, sig, start, 0.22)
    y = lowpass(y, 4200, 63)
    y = reverb(y, 0.38)
    return y


def pluck(freq: float, dur: float, brightness: float, vel: float) -> np.ndarray:
    n = int(dur * SR)
    if n < 8:
        return np.zeros(0)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for k in range(1, 14):
        fk = freq * k * (1 + 0.00035 * k * k)
        if fk > 7500:
            break
        amp = (1.0 / k) * np.exp(-k / brightness)
        decay = np.exp(-t * (2.4 + 1.15 * k))
        y += amp * np.sin(2 * np.pi * fk * t) * decay
    click_n = min(n, 180)
    y[:click_n] += RNG.normal(0, 0.15, click_n) * np.linspace(1, 0, click_n)
    e = env_asr(n, 0.002, 0.03)
    return np.tanh(y * 1.6) * e * vel


def render_guitar() -> np.ndarray:
    y = np.zeros(N)
    for bar in range(BARS):
        st = style_of(bar)
        if st == "intro":
            continue
        tones = GUITAR[chord_of(bar)]
        if st == "verse":
            hits = [(0.0, 0.55, 5.5, 0.55), (2.5, 0.4, 4.2, 0.4)]
        elif st == "break":
            hits = [(0.0, 0.7, 4.0, 0.35)]
        else:
            hits = []
            for i, beat in enumerate((0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5)):
                accent = beat in (0.0, 2.0)
                hits.append((beat, 0.42 if accent else 0.22, 7.0 if accent else 3.6, 0.72 if accent else 0.42))
        direction = 1 if bar % 2 == 0 else -1
        ordered = tones if direction == 1 else tuple(reversed(tones))
        for beat, dur, bright, vel in hits:
            for s_i, midi in enumerate(ordered):
                sig = pluck(midi_hz(midi), dur * BEAT, bright, vel)
                human = float(RNG.uniform(-0.008, 0.01))
                start = (bar * BAR + beat * BEAT) + s_i * 0.012 + human
                mix_in(y, sig, int(round(start * SR)), 0.55)
    y = highpass(y, 90, 63)
    y = reverb(y, 0.26)
    return y


def place_pulses(buf: np.ndarray, t0: float, dur: float, midi: float, vel: float, vib: float) -> None:
    freq = midi_hz(midi)
    i0 = int(round(t0 * SR))
    n = int(round(dur * SR))
    if n < 4 or i0 >= len(buf):
        return
    n = min(n, len(buf) - i0)
    pulse = np.sin(np.linspace(0, np.pi, 24)) ** 2
    a = min(n, int(0.018 * SR))
    r = min(n // 2, int(0.07 * SR))
    i = 0
    while i < n:
        tt = i / SR
        f = freq * (1.0 + vib * np.sin(2 * np.pi * 5.15 * tt))
        env = vel
        if a > 1 and i < a:
            env *= i / a
        if r > 1 and i > n - r:
            env *= max(0.0, (n - i) / r)
        j = i0 + i
        m = min(len(pulse), len(buf) - j)
        if m > 0:
            buf[j : j + m] += pulse[:m] * env
        step = max(1, int(round(SR / max(40.0, f))))
        i += step


def resonator(freq: float, bw: float, seconds: float = 0.06) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.exp(-np.pi * bw * t) * np.sin(2 * np.pi * freq * t)
    return ir


FORMANT_AH = ((730, 80, 1.0), (1120, 100, 0.62), (2500, 150, 0.28), (3400, 180, 0.12))
FORMANT_OO = ((420, 60, 1.0), (860, 80, 0.42), (2200, 140, 0.12))


def apply_formants(src: np.ndarray, formants) -> np.ndarray:
    y = np.zeros_like(src)
    for freq, bw, gain in formants:
        y += gain * fft_conv(src, resonator(freq, bw))
    return y


def sing(events: list[tuple[float, float, float, float]], formants, vib: float) -> np.ndarray:
    exc = np.zeros(N)
    for beat, dur_beats, midi, vel in events:
        place_pulses(exc, beat * BEAT, dur_beats * BEAT, midi, vel, vib)
    if np.max(np.abs(exc)) < 1e-8:
        return exc
    y = apply_formants(exc, formants)
    # aspiration following the excitation
    grain = np.abs(exc)
    kernel = np.exp(-np.arange(int(0.012 * SR)) / (0.003 * SR))
    kernel /= kernel.sum()
    follow = np.convolve(grain, kernel, mode="same")
    noise = highpass(RNG.normal(0, 1, N), 1800, 63)
    peak_f = np.max(follow) or 1.0
    y = y + noise * (follow / peak_f) * (np.max(np.abs(y)) or 1) * 0.05
    y = highpass(y, 130, 63)
    return y


VERSE = [
    (0.0, 0.7, 64, 0.78),
    (1.0, 0.45, 67, 0.7),
    (1.5, 0.4, 69, 0.74),
    (2.0, 1.4, 64, 0.8),
    (4.0, 0.7, 69, 0.76),
    (5.0, 0.4, 67, 0.66),
    (5.5, 0.4, 65, 0.66),
    (6.0, 1.6, 64, 0.78),
    (8.0, 0.45, 64, 0.7),
    (8.5, 0.45, 67, 0.72),
    (9.0, 0.9, 64, 0.74),
    (10.0, 1.4, 62, 0.7),
    (12.0, 0.6, 62, 0.68),
    (13.0, 0.45, 59, 0.62),
    (14.0, 1.5, 62, 0.72),
    (16.0, 0.4, 60, 0.66),
    (16.5, 0.45, 64, 0.72),
    (17.0, 1.3, 69, 0.8),
    (19.0, 0.7, 67, 0.66),
    (20.0, 0.9, 69, 0.78),
    (21.5, 0.4, 67, 0.64),
    (22.0, 1.5, 65, 0.76),
    (24.0, 0.6, 64, 0.72),
    (25.0, 0.4, 62, 0.64),
    (26.0, 0.9, 60, 0.7),
    (27.5, 0.4, 64, 0.6),
    (28.0, 0.9, 62, 0.7),
    (29.5, 0.4, 59, 0.6),
    (30.0, 1.7, 57, 0.78),
]

HOOK = [
    (0.0, 0.45, 69, 0.92),
    (0.5, 0.45, 72, 0.96),
    (1.0, 0.45, 69, 0.88),
    (1.5, 0.4, 64, 0.75),
    (2.0, 1.45, 69, 0.95),
    (4.0, 0.45, 69, 0.88),
    (4.5, 0.7, 72, 0.94),
    (5.5, 0.4, 69, 0.8),
    (6.0, 1.5, 65, 0.9),
    (8.0, 0.45, 67, 0.86),
    (8.5, 0.4, 64, 0.78),
    (9.0, 0.45, 67, 0.84),
    (9.5, 1.0, 69, 0.9),
    (11.0, 0.7, 67, 0.75),
    (12.0, 0.45, 64, 0.8),
    (12.5, 0.4, 62, 0.72),
    (13.0, 0.45, 59, 0.7),
    (14.0, 1.6, 62, 0.88),
]

HOOK_A = [ev for ev in HOOK if ev[0] < 8]

ENDING = [
    (0.0, 0.5, 69, 0.9),
    (0.5, 0.5, 72, 0.92),
    (1.0, 1.0, 69, 0.88),
    (2.2, 1.4, 64, 0.8),
    (4.0, 0.8, 67, 0.78),
    (5.0, 0.45, 64, 0.7),
    (5.6, 0.4, 62, 0.62),
    (6.2, 1.6, 57, 0.9),
]

BREAK_MEL = [
    (0.0, 3.4, 64, 0.62),
    (4.0, 3.2, 65, 0.6),
    (8.0, 1.4, 64, 0.58),
    (10.0, 1.4, 67, 0.6),
    (12.0, 1.3, 62, 0.55),
    (14.0, 1.5, 59, 0.55),
]


def shift_phrase(phrase, start_beat, vel_scale=1.0):
    return [(start_beat + b, d, m, v * vel_scale) for b, d, m, v in phrase]


def render_lead() -> np.ndarray:
    events = []
    events += shift_phrase(VERSE, 4 * 4, 0.92)  # bar 4, beat 16
    for bar in (12, 16, 24):
        events += shift_phrase(HOOK, bar * 4, 1.0)
    events += shift_phrase(HOOK_A, 28 * 4, 1.0)
    events += shift_phrase(ENDING, 30 * 4, 0.95)
    events += shift_phrase(BREAK_MEL, 20 * 4, 0.85)
    y = sing(events, FORMANT_AH, vib=0.012)
    # dotted-eighth slap delay, one musical repeat
    delay = int(round(0.75 * BEAT * SR))
    echoed = np.zeros_like(y)
    echoed[delay:] += y[:-delay] * 0.26
    delay2 = delay * 2
    if delay2 < len(y):
        echoed[delay2:] += y[:-delay2] * 0.1
    y = y + echoed
    y = reverb(y, 0.24)
    return y


def render_backing() -> np.ndarray:
    events = []
    sustains = {0: 60, 1: 57, 2: 64, 3: 59}  # thirds: C4 A3 E4 B3
    hits = [(0.0, 0.42, 64, 0.62), (0.5, 0.42, 67, 0.55), (1.0, 0.42, 64, 0.5)]
    for bar in (12, 16, 24, 28):
        # 4 bars, but bar 28 block is special: only 2 bars of hook then ending bed
        length = 2 if bar == 28 else 4
        for i in range(length):
            b = bar + i
            if b >= 30:
                break
            events.append((b * 4, 3.1, sustains[b % 4], 0.5))
            events += shift_phrase(hits, b * 4, 0.85)
        if bar != 28:
            # answer phrase, bar+1, softer third-above on the long note region
            events.append(((bar + 1) * 4 + 2.0, 1.2, 72 if (bar + 1) % 4 == 1 else 69, 0.28))
    # ending bed on Am
    events.append((30 * 4, 3.2, 60, 0.42))  # C4
    events.append((31 * 4, 2.4, 64, 0.36))  # E4
    y = sing(events, FORMANT_OO, vib=0.008)
    y = reverb(y, 0.36)
    return y


def fade_out(x: np.ndarray) -> np.ndarray:
    y = x.copy()
    # musical fade across the last 2 bars, then a short safety fade
    start = int(round(30 * BAR * SR))
    if start < len(y):
        ramp = np.linspace(1.0, 0.0, len(y) - start)
        # keep a little longer than linear at first
        ramp = ramp ** 1.15
        y[start:] *= ramp
    edge = int(0.01 * SR)
    y[:edge] *= np.linspace(0, 1, edge)
    return y


def peak_of(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if len(x) else 0.0


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def to_peaks(x: np.ndarray, bars: int = 96) -> list[float]:
    # use the musical body, not the silent tail, so the waveform matches the timeline
    body = x[: int(SONG * SR)]
    n = len(body)
    edges = np.linspace(0, n, bars + 1).astype(int)
    vals = []
    for i in range(bars):
        seg = body[edges[i] : edges[i + 1]]
        if len(seg) == 0:
            vals.append(0.0)
            continue
        # stride for speed
        vals.append(float(np.max(np.abs(seg[::8]))))
    m = max(vals) or 1.0
    return [round(v / m, 4) for v in vals]


def write_wav(path: Path, x: np.ndarray) -> None:
    import wave

    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> None:
    print(f"Rendering {TOTAL:.2f}s @ {SR} Hz, {BPM} BPM, {BARS} bars, N={N}")
    stems = {
        "drums": render_drums(),
        "bass": render_bass(),
        "keys": render_keys(),
        "guitar": render_guitar(),
        "vocals": render_lead(),
        "backing": render_backing(),
    }
    print("Rendered. Balancing…")
    # The vocal resonator is much hotter than the rhythm section.
    # Peak-balance each stem first so one voice cannot crush the mix.
    targets = {
        "drums": 0.90,
        "bass": 0.72,
        "keys": 0.48,
        "guitar": 0.46,
        "vocals": 0.62,
        "backing": 0.40,
    }
    for name, target in targets.items():
        stems[name] = fade_out(stems[name])
        pk = peak_of(stems[name]) or 1.0
        stems[name] *= target / pk

    mix = np.sum(np.stack(list(stems.values())), axis=0)
    scale = 0.92 / (peak_of(mix) or 1.0)
    if scale < 1:
        for name in stems:
            stems[name] *= scale
    else:
        scale = 1.0
    mix = np.sum(np.stack(list(stems.values())), axis=0)

    print(f"scale={scale:.3f} mix_peak={peak_of(mix):.3f} mix_rms={rms(mix):.3f}")
    for bar in range(BARS):
        a = int(bar * BAR * SR)
        b = int((bar + 1) * BAR * SR)
        parts = " ".join(f"{k[:3]}={rms(stems[k][a:b]):.3f}" for k in ("drums", "bass", "keys", "guitar", "vocals", "backing"))
        print(f"bar {bar:02d} {style_of(bar)[:3]} {chord_of(bar):2} {parts}")

    AUDIO.mkdir(parents=True, exist_ok=True)
    peaks = {"duration": round(TOTAL, 3), "bpm": BPM, "sampleRate": SR, "stems": {}}
    for name, audio in stems.items():
        wav = AUDIO / f"{name}.wav"
        mp3 = AUDIO / f"{name}.mp3"
        write_wav(wav, audio)
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(wav),
                "-codec:a", "libmp3lame",
                "-b:a", "128k",
                "-ac", "1",
                str(mp3),
            ]
        )
        wav.unlink()
        peaks["stems"][name] = to_peaks(audio)
        print(f"{name:8} peak={peak_of(audio):.3f} rms={rms(audio):.3f} bytes={mp3.stat().st_size}")

    # QA mixdown (not shipped)
    mix_path = Path("/tmp/stems-qa/mix.wav")
    mix_path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(mix_path, np.clip(mix, -1, 1) * (0.9 / (peak_of(mix) or 1)))
    (AUDIO / "peaks.json").write_text(json.dumps(peaks))
    print("peaks.json written")


if __name__ == "__main__":
    main()
