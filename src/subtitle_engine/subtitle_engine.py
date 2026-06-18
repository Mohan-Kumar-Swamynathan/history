"""Premium Tamil subtitles — SRT, ASS, and burn-in."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.core.config_loader import resolve_font_path
from src.core.models import WordTiming

log = logging.getLogger(__name__)


class SubtitleEngine:
    def write_srt(self, word_timings: List[WordTiming], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for index, timing in enumerate(word_timings, start=1):
            lines.append(str(index))
            lines.append(f"{_ms_to_srt(timing.start_ms)} --> {_ms_to_srt(timing.end_ms)}")
            lines.append(timing.word)
            lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    def write_ass(
        self,
        word_timings: List[WordTiming],
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        margin_v = 80 if height > width else 140
        font_size = 56 if height <= width else 48
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Tamil,{font_size},&H00000000,&H000000FF,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for timing in word_timings:
            highlighted = f"{{\\c&H001923CD&}}{timing.word}{{\\c&H00000000&}}"
            events.append(
                f"Dialogue: 0,{_ms_to_ass(timing.start_ms)},{_ms_to_ass(timing.end_ms)},"
                f"Default,,0,0,0,,{highlighted}"
            )
        output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        return output_path

    def burn_ass_into_video(
        self,
        video_path: Path,
        ass_path: Path,
        output_path: Path,
        word_timings: List[WordTiming] | None = None,
        fps: int = 24,
    ) -> Path:
        if self._ffmpeg_has_subtitles_filter():
            burned = self._burn_with_ffmpeg_subtitles(video_path, ass_path, output_path)
            if burned:
                return output_path
        if word_timings:
            return self._burn_with_pil_overlay(video_path, word_timings, output_path, fps)
        import shutil
        shutil.copy(video_path, output_path)
        return output_path

    def _ffmpeg_has_subtitles_filter(self) -> bool:
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True,
            text=True,
            check=False,
        )
        combined = result.stdout + result.stderr
        return " subtitles " in combined or "\nsubtitles " in combined

    def _burn_with_ffmpeg_subtitles(
        self,
        video_path: Path,
        ass_path: Path,
        output_path: Path,
    ) -> bool:
        work_dir = video_path.parent
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video_path.name,
            "-vf",
            f"subtitles={ass_path.name}",
            "-c:a",
            "copy",
            str(output_path.resolve()),
        ]
        result = subprocess.run(command, cwd=work_dir, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            log.warning("FFmpeg subtitle burn failed: %s", result.stderr.strip())
            return False
        return True

    def _burn_with_pil_overlay(
        self,
        video_path: Path,
        word_timings: List[WordTiming],
        output_path: Path,
        fps: int,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        width_str, height_str = probe.stdout.strip().split(",")
        width, height = int(width_str), int(height_str)

        font_path = resolve_font_path("ta_bold")
        font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        highlight_color = (205, 35, 25)
        normal_color = (20, 20, 20)

        decode_command = [
            "ffmpeg", "-loglevel", "error",
            "-i", str(video_path),
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        decode_process = subprocess.Popen(decode_command, stdout=subprocess.PIPE)
        encode_command = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps),
            "-i", "pipe:0",
            "-i", str(video_path),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path),
        ]
        encode_process = subprocess.Popen(encode_command, stdin=subprocess.PIPE)
        assert decode_process.stdout is not None
        assert encode_process.stdin is not None

        frame_bytes = width * height * 3
        frame_index = 0
        while True:
            raw = decode_process.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            current_ms = int((frame_index / fps) * 1000)
            image = Image.frombytes("RGB", (width, height), raw)
            self._draw_subtitle_bar(image, word_timings, current_ms, font, normal_color, highlight_color)
            encode_process.stdin.write(np.array(image).tobytes())
            frame_index += 1

        decode_process.stdout.close()
        decode_process.wait()
        encode_process.stdin.close()
        encode_process.wait()
        return output_path

    def _draw_subtitle_bar(
        self,
        image: Image.Image,
        word_timings: List[WordTiming],
        current_ms: int,
        font: ImageFont.ImageFont,
        normal_color: tuple[int, int, int],
        highlight_color: tuple[int, int, int],
    ) -> None:
        visible = [timing for timing in word_timings if timing.start_ms <= current_ms]
        if not visible:
            return
        draw = ImageDraw.Draw(image)
        width, height = image.size
        line_words = visible[-12:]
        current_word = None
        for timing in word_timings:
            if timing.start_ms <= current_ms < timing.end_ms:
                current_word = timing.word
                break

        x_cursor = 80
        y_base = height - (140 if height > width else 90)
        for timing in line_words:
            color = highlight_color if timing.word == current_word else normal_color
            draw.text((x_cursor, y_base), timing.word, font=font, fill=color)
            bbox = draw.textbbox((x_cursor, y_base), timing.word, font=font)
            x_cursor = bbox[2] + 14
            if x_cursor > width - 80:
                break


def _ms_to_srt(milliseconds: int) -> str:
    hours = milliseconds // 3_600_000
    minutes = (milliseconds % 3_600_000) // 60_000
    seconds = (milliseconds % 60_000) // 1000
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _ms_to_ass(milliseconds: int) -> str:
    hours = milliseconds // 3_600_000
    minutes = (milliseconds % 3_600_000) // 60_000
    seconds = (milliseconds % 60_000) // 1000
    centis = (milliseconds % 1000) // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"
