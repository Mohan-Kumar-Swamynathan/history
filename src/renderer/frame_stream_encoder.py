"""Stream frames to FFmpeg without holding the full video in memory."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import numpy as np


class FrameStreamEncoder:
    def __init__(self, output_path: Path, width: int, height: int, fps: int) -> None:
        self._output_path = output_path
        self._width = width
        self._height = height
        self._fps = fps
        self._frame_count = 0
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{width}x{height}",
            "-pix_fmt",
            "rgb24",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE)
        if self._process.stdin is None:
            raise RuntimeError("FFmpeg stdin unavailable for frame streaming")

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def write_frames(self, frames: List[np.ndarray]) -> None:
        for frame in frames:
            self.write_frame(frame)

    def write_frame(self, frame: np.ndarray) -> None:
        if frame.shape[0] != self._height or frame.shape[1] != self._width:
            from PIL import Image

            frame = np.array(
                Image.fromarray(frame).resize((self._width, self._height), Image.LANCZOS)
            )
        self._process.stdin.write(frame.tobytes())
        self._frame_count += 1

    def close(self) -> Path:
        self._process.stdin.close()
        return_code = self._process.wait()
        if return_code != 0:
            raise RuntimeError("FFmpeg frame streaming failed")
        return self._output_path
