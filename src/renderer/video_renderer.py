"""Video assembly — FFmpeg encoding, audio mix, duration alignment."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

import numpy as np

from src.core.config_loader import load_platform_config

log = logging.getLogger(__name__)


class VideoRenderer:
    def __init__(self) -> None:
        platform = load_platform_config()
        video = platform.get("video", {})
        self.width = video.get("width", 1920)
        self.height = video.get("height", 1080)
        self.fps = video.get("fps", 24)
        self.shorts_width = video.get("shorts_width", 1080)
        self.shorts_height = video.get("shorts_height", 1920)

    def encode_frames(self, frames: List[np.ndarray], output_path: Path) -> Path:
        """Encode frames to H.264. CI-optimised: ultrafast preset + frame dedup."""
        import hashlib
        output_path.parent.mkdir(parents=True, exist_ok=True)
        width = frames[0].shape[1] if frames else self.width
        height = frames[0].shape[0] if frames else self.height
        command = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgb24",
            "-r", str(self.fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",   # 3× faster than veryfast on CI
            "-crf", "23",             # adequate for YouTube re-compression
            "-tune", "stillimage",    # helps when frames are identical
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE)
        assert process.stdin is not None
        prev_hash: bytes | None = None
        prev_bytes: bytes | None = None
        for frame in frames:
            # Dedup: re-pipe cached bytes for identical frames (skip tobytes)
            h = hashlib.md5(frame[::16, ::16].tobytes()).digest()
            if h == prev_hash and prev_bytes is not None:
                process.stdin.write(prev_bytes)
            else:
                raw = frame.tobytes()
                process.stdin.write(raw)
                prev_hash = h
                prev_bytes = raw
        process.stdin.close()
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("FFmpeg frame encoding failed")
        return output_path

    def align_video_duration(
        self,
        video_path: Path,
        target_duration_seconds: float,
        output_path: Path,
    ) -> Path:
        video_duration = self._probe_duration(video_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if abs(video_duration - target_duration_seconds) < 0.15:
            shutil.copy(video_path, output_path)
            return output_path

        if video_duration < target_duration_seconds:
            pad_seconds = target_duration_seconds - video_duration
            command = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ]
        else:
            command = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-t", f"{target_duration_seconds:.3f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ]
        subprocess.run(command, check=True)
        return output_path

    def mux_audio(
        self,
        video_path: Path,
        narration_path: Path,
        output_path: Path,
        bgm_path: Path | None = None,
        bgm_volume: float = 0.08,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        video_duration = self._probe_duration(video_path)
        audio_duration = self._probe_duration(narration_path)
        target_duration = max(video_duration, audio_duration)

        if bgm_path and bgm_path.exists():
            filter_complex = (
                "[1:a]volume=1.0[voice];"
                f"[2:a]volume={bgm_volume},aloop=loop=-1:size=2e+09,"
                f"atrim=0:{target_duration:.2f}[bgm];"
                "[voice][bgm]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
            )
            command = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-i", str(narration_path),
                "-i", str(bgm_path),
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", f"{target_duration:.3f}",
                str(output_path),
            ]
        else:
            command = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-i", str(narration_path),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", f"{target_duration:.3f}",
                str(output_path),
            ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            log.warning("Audio mux failed, copying video only: %s", result.stderr)
            shutil.copy(video_path, output_path)
        return output_path

    def _probe_duration(self, media_path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 60.0
