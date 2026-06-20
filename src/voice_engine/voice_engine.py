"""Edge TTS voice generation — per-beat synthesis with timing.

v2 — pronunciation fixes:
  1. Pre-process Tamil+English mixed text before TTS:
     - Transliterate common English proper nouns to Tamil phonetics
     - Spell out standalone numbers in Tamil words
     - Insert SSML-style pauses at sentence boundaries
  2. Slightly slower rate (-8%) for clarity on proper nouns
  3. Female voice (PallaviNeural) as default — clearer on mixed text
"""

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

# ── Tamil phonetic substitutions for common English proper nouns ─────
# Key: regex pattern (case-insensitive), Value: Tamil phonetic spelling
_EN_TO_TA: list[tuple[str, str]] = [
    # People
    (r"\bColonel Sanders\b",  "கர்னல் சாண்டர்ஸ்"),
    (r"\bSteve Jobs\b",       "ஸ்டீவ் ஜாப்ஸ்"),
    (r"\bElon Musk\b",        "எலான் மஸ்க்"),
    (r"\bAbdul Kalam\b",      "அப்துல் கலாம்"),
    (r"\bIndra Nooyi\b",      "இந்திரா நூயி"),
    (r"\bJeff Bezos\b",       "ஜெஃப் பெசோஸ்"),
    (r"\bWarren Buffett\b",   "வாரன் பஃபெட்"),
    (r"\bNarayana Murthy\b",  "நாராயண மூர்த்தி"),
    (r"\bRatan Tata\b",       "ரத்தன் டாட்டா"),
    (r"\bDhirubhai Ambani\b", "திருபாய் அம்பானி"),
    # Companies
    (r"\bNokia\b",     "நோக்கியா"),
    (r"\bApple\b",     "ஆப்பிள்"),
    (r"\bGoogle\b",    "கூகுள்"),
    (r"\bAmazon\b",    "அமேசான்"),
    (r"\bKFC\b",       "கே எஃப் சி"),
    (r"\bPepsi\b",     "பெப்சி"),
    (r"\bMicrosoft\b", "மைக்ரோசாஃப்ட்"),
    (r"\bTwitter\b",   "ட்விட்டர்"),
    (r"\bYouTube\b",   "யூட்யூப்"),
    (r"\bFacebook\b",  "ஃபேஸ்புக்"),
    (r"\bWikipedia\b", "விக்கிபீடியா"),
    # Places
    (r"\bKentucky\b",     "கென்டக்கி"),
    (r"\bSilicon Valley\b","சிலிக்கன் வேலி"),
    (r"\bFinland\b",      "ஃபின்லாந்து"),
    (r"\bJapan\b",        "ஜப்பான்"),
    (r"\bChina\b",        "சீனா"),
    (r"\bAmerica\b",      "அமெரிக்கா"),
    (r"\bUSA\b",          "அமெரிக்கா"),
    # Numbers — spell out common ones in Tamil
    (r"\b1009\b", "ஆயிரத்து ஒன்பது"),
    (r"\b108\b",  "நூற்றி எட்டு"),
    (r"\b1000\b", "ஆயிரம்"),
    (r"\b100\b",  "நூறு"),
    (r"\b(\d+)%\b", r"\1 சதவீதம்"),
]

# ── Number-to-Tamil-word for isolated digit sequences ────────────────
_ONES = ["", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து",
         "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"]
_TENS = ["", "பத்து", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது",
         "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"]


def _num_to_ta(n: int) -> str:
    """Convert integer 1-999 to Tamil word."""
    if n <= 0 or n >= 1000:
        return str(n)
    if n < 10:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (" " + _ONES[ones] if ones else "")
    hundreds, rest = divmod(n, 100)
    prefix = (_ONES[hundreds] + " நூறு") if hundreds > 1 else "நூறு"
    return prefix + (" " + _num_to_ta(rest) if rest else "")


def preprocess_tts_text(text: str) -> str:
    """Clean text for TTS — fix hyphens, numbers, English mixing.

    Critical fixes:
    1. "1950-ல்" → "1950 ஆம் ஆண்டில்" (hyphen before Tamil suffix)
    2. "65-வது" → "அறுபத்தி ஐந்தாவது"
    3. Replace known English proper nouns with Tamil phonetics
    4. Spell out small numbers in Tamil
    """
    # Fix 0: year-Tamil suffix patterns (most common robotic sound)
    # "1950-ல்" → "1950 ஆம் ஆண்டில்"
    text = re.sub(r'(\d{4})-ல்', r'\1 ஆம் ஆண்டில்', text)
    text = re.sub(r'(\d{4})-இல்', r'\1 ஆம் ஆண்டில்', text)
    text = re.sub(r'(\d{4})-ம்', r'\1 ஆம்', text)
    # "65-வது" → ordinal in Tamil
    text = re.sub(r'(\d+)-வது', lambda m: _num_to_ta(int(m.group(1))) + 'வது', text)
    text = re.sub(r'(\d+)-ஆவது', lambda m: _num_to_ta(int(m.group(1))) + ' ஆவது', text)
    # General: remove hyphen between number and Tamil suffix
    text = re.sub(r'(\d+)-([\u0B80-\u0BFF])', r'\1 \2', text)

    # Fix 1: known English → Tamil substitutions
    for pattern, replacement in _EN_TO_TA:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Fix 2: standalone numbers → Tamil words
    def _replace_number(m: re.Match) -> str:
        n = int(m.group())
        if 2 <= n <= 999:
            return _num_to_ta(n)
        return m.group()
    text = re.sub(r'(?<!\d)\b([2-9]\d{0,2})\b(?!\d)', _replace_number, text)

    # Fix 3: remove remaining English words not in substitution list
    # Replace with Tamil transliteration hint or remove
    def _handle_english(m: re.Match) -> str:
        word = m.group()
        if len(word) <= 3: return word  # short codes OK
        return word  # keep — TTS will attempt it
    text = re.sub(r'\b[A-Za-z]{4,}\b', _handle_english, text)

    # Fix 4: normalise punctuation
    text = re.sub(r'\.\s+', '. ', text)
    text = re.sub(r'!\s+', '! ', text)
    text = re.sub(r'\?\s+', '? ', text)

    return text.strip()


def _is_known_english(word: str) -> bool:
    """True if the word was already transliterated or should stay."""
    # After substitution pass, remaining English is either:
    # - Short abbreviations (OK to keep) or unknown proper nouns
    # We keep all — edge-tts handles them better than silence
    return True


class VoiceEngine:
    def __init__(self, voice_key: str = "default") -> None:
        voice_config = load_voice_config()
        if voice_key == "female":
            self.voice = voice_config.get("female_voice", "ta-IN-PallaviNeural")
        else:
            # PallaviNeural handles Tamil+English mixing better than ValluvarNeural
            self.voice = voice_config.get("default_voice", "ta-IN-PallaviNeural")
        # Slightly slower rate improves clarity on proper nouns and numbers
        self.rate  = voice_config.get("rate",  "-8%")
        self.pitch = voice_config.get("pitch", "+0Hz")
        self.pause_between_beats_ms = int(voice_config.get("pause_between_beats_ms", 500))

    def synthesize_all_beats(self, beats: List[StoryBeat], audio_dir: Path) -> NarrationBundle:
        audio_dir.mkdir(parents=True, exist_ok=True)
        segments: List[BeatAudioSegment] = []
        all_timings: List[WordTiming] = []
        global_offset_ms = 0
        beat_paths: List[Path] = []

        for index, beat in enumerate(beats):
            beat_path = audio_dir / f"beat_{index:02d}.mp3"
            # Pre-process for better pronunciation before sending to TTS
            clean_text = preprocess_tts_text(beat.narration_ta)
            duration_seconds, beat_timings = asyncio.run(
                self._synthesize_beat_async(clean_text, beat_path)
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
            # Use original text words for subtitle timing (not transliterated)
            original_timings = self._build_word_timings_from_audio(beat.narration_ta, duration_seconds)
            for timing in original_timings:
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
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
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
