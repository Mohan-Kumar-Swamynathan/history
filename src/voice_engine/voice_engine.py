"""Edge TTS voice generation — per-beat synthesis with timing."""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

from src.core.config_loader import load_voice_config
from src.core.models import BeatAudioSegment, NarrationBundle, StoryBeat, WordTiming

log = logging.getLogger(__name__)


class VoiceEngine:
    def __init__(self, voice_key: str = "default") -> None:
        voice_config = load_voice_config()
        if voice_key == "female":
            self.voice = voice_config.get("female_voice", "ta-IN-PallaviNeural")
        else:
            self.voice = voice_config.get("default_voice", "ta-IN-ValluvarNeural")
        self.rate = voice_config.get("rate", "+0%")
        self.pitch = voice_config.get("pitch", "+0Hz")
        self.pause_between_beats_ms = int(voice_config.get("pause_between_beats_ms", 400))

    def synthesize_all_beats(self, beats: List[StoryBeat], audio_dir: Path) -> NarrationBundle:
        audio_dir.mkdir(parents=True, exist_ok=True)
        segments: List[BeatAudioSegment] = []
        all_timings: List[WordTiming] = []
        global_offset_ms = 0
        beat_paths: List[Path] = []

        for index, beat in enumerate(beats):
            beat_path = audio_dir / f"beat_{index:02d}.mp3"
            duration_seconds, beat_timings = asyncio.run(
                self._synthesize_beat_async(beat.narration_ta, beat_path)
            )
            segments.append(
                BeatAudioSegment(
                    beat_index=index,
                    audio_path=str(beat_path),
                    duration_seconds=duration_seconds,
                    word_timings=beat_timings,
                    start_ms=global_offset_ms,
                )
            )
            for timing in beat_timings:
                all_timings.append(
                    WordTiming(
                        word=timing.word,
                        start_ms=global_offset_ms + timing.start_ms,
                        end_ms=global_offset_ms + timing.end_ms,
                    )
                )
            beat_paths.append(beat_path)
            global_offset_ms += int(duration_seconds * 1000) + self.pause_between_beats_ms

        narration_path = audio_dir / "narration.mp3"
        total_duration = self._concatenate_audio_files(
            beat_paths,
            narration_path,
            pause_ms=self.pause_between_beats_ms,
        )
        return NarrationBundle(
            narration_path=str(narration_path),
            segments=segments,
            all_word_timings=all_timings,
            total_duration_seconds=total_duration,
        )

    def synthesize_beats(self, beats: List[StoryBeat], output_path: Path) -> Tuple[Path, List[WordTiming]]:
        bundle = self.synthesize_all_beats(beats, output_path.parent)
        return Path(bundle.narration_path), bundle.all_word_timings

    async def _synthesize_beat_async(self, text: str, output_path: Path) -> Tuple[float, List[WordTiming]]:
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
        await communicate.save(str(output_path))
        duration_seconds = self._get_audio_duration(output_path)
        word_timings = self._build_word_timings_from_audio(text, duration_seconds)
        return duration_seconds, word_timings

    def _build_word_timings_from_audio(self, text: str, duration_seconds: float) -> List[WordTiming]:
        words = re.findall(r"\S+", text)
        if not words:
            return []
        total_duration_ms = int(duration_seconds * 1000)
        weights = [max(len(word), 1) for word in words]
        weight_sum = sum(weights)
        timings: List[WordTiming] = []
        cursor_ms = 0
        for word, weight in zip(words, weights):
            word_duration_ms = max(80, int(total_duration_ms * weight / weight_sum))
            timings.append(
                WordTiming(word=word, start_ms=cursor_ms, end_ms=cursor_ms + word_duration_ms)
            )
            cursor_ms += word_duration_ms
        if timings and cursor_ms != total_duration_ms:
            timings[-1].end_ms = total_duration_ms
        return timings

    def _concatenate_audio_files(
        self,
        audio_paths: List[Path],
        output_path: Path,
        pause_ms: int,
    ) -> float:
        if not audio_paths:
            raise ValueError("No beat audio files to concatenate")

        pause_path = output_path.parent / "_pause.mp3"
        pause_seconds = pause_ms / 1000.0
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", str(pause_seconds),
                "-c:a", "libmp3lame", "-b:a", "128k",
                str(pause_path),
            ],
            check=True,
        )

        concat_list = output_path.parent / "concat_audio.txt"
        lines: List[str] = []
        for index, path in enumerate(audio_paths):
            lines.append(f"file '{path.resolve()}'")
            if index < len(audio_paths) - 1:
                lines.append(f"file '{pause_path.resolve()}'")
        concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-af", "aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono",
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(output_path),
            ],
            check=True,
        )
        return self._get_audio_duration(output_path)

    def _get_audio_duration(self, audio_path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 3.0
