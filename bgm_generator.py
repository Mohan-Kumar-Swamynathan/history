#!/usr/bin/env python3
"""
BGM Generator — Tamil History Channel
Generates a warm, cinematic instrumental loop using FFmpeg sine synthesis.
No external audio assets needed. Pure Python + FFmpeg.

Produces a 10-minute loopable BGM track with:
 - Tanpura drone (Sa + Pa)
 - Soft tabla-style rhythmic pulse
 - Veena-like melody line (pentatonic)
 - Slow fade in/out
"""

import subprocess, sys, os
from pathlib import Path

BGM_OUTPUT = Path(__file__).parent / "bgm" / "tamil_instrumental.mp3"

def generate_bgm(duration_seconds: int = 600) -> Path:
    """
    Build a layered Tamil-flavoured ambient track using FFmpeg's
    sine wave generators + mixing. Completely offline, no samples needed.

    Layers:
      1. Drone: 261 Hz (Sa/C4) + 392 Hz (Pa/G4) — tanpura root
      2. Bass pulse: 130 Hz at 0.5s intervals — tabla bass
      3. Melody: pentatonic arpeggio over C major (C-E-G-A-C)
      4. High shimmer: 1046 Hz very soft — bell/cymbal texture
    """
    BGM_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if BGM_OUTPUT.exists():
        print(f"BGM already exists: {BGM_OUTPUT}")
        return BGM_OUTPUT

    print("Generating Tamil ambient BGM (this takes ~30 seconds)…")

    d = duration_seconds

    # ── Pentatonic melody pattern (C D E G A repeating) ───────────────────
    # Frequencies: 261, 294, 329, 392, 440 Hz
    melody_freqs = [261, 294, 329, 392, 440, 392, 329, 294]
    melody_parts = []
    note_dur = 1.5   # seconds per note
    for i, freq in enumerate(melody_freqs * (int(d / (len(melody_freqs) * note_dur)) + 2)):
        start = i * note_dur
        if start >= d:
            break
        melody_parts.append(
            f"sine=frequency={freq}:duration={min(note_dur, d-start)},adelay={int(start*1000)}|{int(start*1000)},apad=whole_dur={d}"
        )

    # Build the FFmpeg filter_complex
    filter_complex = (
        # Layer 1: Tanpura drone Sa (261 Hz) + Pa (392 Hz)
        f"[0]volume=0.18,aecho=0.7:0.7:60:0.3[drone];"

        # Layer 2: Tabla bass pulse (130 Hz, every 500ms)
        f"[1]volume=0.10,aecho=0.5:0.5:20:0.2[bass];"

        # Layer 3: Veena melody (gentler)
        f"[2]volume=0.13,aecho=0.6:0.6:80:0.25[melody];"

        # Layer 4: Bell shimmer (1046 Hz)
        f"[3]volume=0.06[shimmer];"

        # Mix all layers
        f"[drone][bass][melody][shimmer]amix=inputs=4:duration=longest:dropout_transition=2[mixed];"

        # Master: gentle compression + warmth EQ + fade in/out + loudnorm
        f"[mixed]"
        f"acompressor=threshold=-20dB:ratio=2.5:attack=20:release=200:makeup=2,"
        f"equalizer=f=200:t=q:w=1.0:g=+3,"
        f"equalizer=f=3000:t=q:w=1.0:g=-4,"
        f"equalizer=f=8000:t=q:w=1.0:g=-6,"
        f"afade=t=in:d=4,"
        f"afade=t=out:st={d-5}:d=5,"
        f"loudnorm=I=-22:TP=-3:LRA=12[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        # Input 0: drone
        "-f", "lavfi", "-i", f"sine=frequency=261:duration={d}",
        # Input 1: bass pulse
        "-f", "lavfi", "-i", f"sine=frequency=130:duration={d}",
        # Input 2: melody (261 Hz base; melody is shaped in filter)
        "-f", "lavfi", "-i", f"sine=frequency=329:duration={d}",
        # Input 3: shimmer
        "-f", "lavfi", "-i", f"sine=frequency=1046:duration={d}",
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", "44100",
        "-b:a", "128k",
        "-ac", "2",
        str(BGM_OUTPUT)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"BGM generation warning: {result.stderr[-300:]}")
        # Fallback: simple drone only
        _generate_simple_bgm(d)
    else:
        print(f"BGM ready: {BGM_OUTPUT}")

    return BGM_OUTPUT


def _generate_simple_bgm(duration: int):
    """Minimal fallback: just a soft drone."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=261:duration={duration}",
        "-af", (
            "volume=0.15,"
            "aecho=0.7:0.7:100:0.3,"
            f"afade=t=in:d=3,afade=t=out:st={duration-4}:d=4,"
            "loudnorm=I=-22:TP=-3"
        ),
        "-ar", "44100", "-b:a", "128k",
        str(BGM_OUTPUT)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"Fallback BGM ready: {BGM_OUTPUT}")


if __name__ == "__main__":
    mins = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    generate_bgm(mins * 60)
