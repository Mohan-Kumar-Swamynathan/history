"""Emotion-aware BGM generator using FFmpeg — 100% free."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.config_loader import load_emotions_config


def generate_bgm(
    output_path: Path,
    duration_seconds: int = 120,
    dominant_emotion: str = "neutral",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        return output_path

    emotions = load_emotions_config()
    emotion_cfg = emotions.get(dominant_emotion, emotions.get("neutral", {}))
    master_volume = float(emotion_cfg.get("bgm_volume", 0.08))

    if dominant_emotion == "sad":
        return _generate_sad_drone(output_path, duration_seconds, master_volume)
    if dominant_emotion == "exciting":
        return _generate_exciting_arpeggio(output_path, duration_seconds, master_volume)
    if dominant_emotion in {"inspirational", "hope"}:
        return _generate_inspirational_melody(output_path, duration_seconds, master_volume)
    return _generate_neutral_ambient(output_path, duration_seconds, master_volume)


def _generate_sad_drone(output_path: Path, duration: int, volume: float) -> Path:
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=130:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=196:duration={duration}",
        "-filter_complex",
        (
            f"[0:a]volume={volume * 1.2}[a0];"
            f"[1:a]volume={volume * 0.8}[a1];"
            "[a0][a1]amix=inputs=2:duration=first,"
            "aecho=0.8:0.8:120:0.35,"
            f"afade=t=in:d=3,afade=t=out:st={max(1, duration - 4)}:d=4"
        ),
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def _generate_exciting_arpeggio(output_path: Path, duration: int, volume: float) -> Path:
    freqs = [261, 329, 392, 523, 392, 329]
    note_dur = 0.6
    parts = []
    for index, freq in enumerate(freqs * (int(duration / (len(freqs) * note_dur)) + 2)):
        start = index * note_dur
        if start >= duration:
            break
        parts.append(
            f"sine=frequency={freq}:duration={min(note_dur, duration - start)}"
        )
    melody_input = "|".join(parts[:1]) if len(parts) == 1 else parts[0]
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=130:duration={duration}",
        "-f", "lavfi", "-i", melody_input,
        "-filter_complex",
        (
            f"[0:a]volume={volume * 0.9}[bass];"
            f"[1:a]volume={volume * 1.1},aecho=0.4:0.4:40:0.2[melody];"
            "[bass][melody]amix=inputs=2:duration=first"
        ),
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def _generate_inspirational_melody(output_path: Path, duration: int, volume: float) -> Path:
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=261:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=392:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=523:duration={duration}",
        "-filter_complex",
        (
            f"[0:a]volume={volume * 0.7}[drone];"
            f"[1:a]volume={volume * 0.5}[pa];"
            f"[2:a]volume={volume * 0.4},aecho=0.6:0.6:80:0.25[high];"
            "[drone][pa][high]amix=inputs=3:duration=first,"
            f"afade=t=in:d=4,afade=t=out:st={max(1, duration - 5)}:d=5"
        ),
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def _generate_neutral_ambient(output_path: Path, duration: int, volume: float) -> Path:
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=261:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=392:duration={duration}",
        "-filter_complex",
        (
            f"[0:a]volume={volume}[a0];"
            f"[1:a]volume={volume * 0.6}[a1];"
            "[a0][a1]amix=inputs=2:duration=first"
        ),
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path
