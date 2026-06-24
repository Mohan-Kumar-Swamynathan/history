"""Pexels stock video engine — beat-synced clips with Ken Burns fallback."""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional, Sequence

from src.image_engine.image_engine import _build_query

log = logging.getLogger(__name__)

USE_STOCK_VIDEO = os.environ.get("USE_STOCK_VIDEO", "true").lower() not in ("false", "0", "no")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_VIDEOS_SEARCH_URL = "https://api.pexels.com/videos/search"
MIN_STOCK_VIDEO_WIDTH = 720
SHORT_MAX_DURATION_SECONDS = 55.0

KB_ZOOM_IN = "min(1.0+0.0008*on,1.20)"
KB_PAN_RIGHT = "iw/2-(iw/zoom/2)+on*0.3"
KB_PAN_CENTER = "ih/2-(ih/zoom/2)"


def is_stock_video_enabled() -> bool:
    return bool(PEXELS_API_KEY) and USE_STOCK_VIDEO


def require_stock_video_enabled() -> None:
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY is required for stock video rendering")
    if not USE_STOCK_VIDEO:
        raise RuntimeError("USE_STOCK_VIDEO is disabled")


def build_beat_scenes(beats: Sequence) -> List[Dict]:
    """One stock scene per narrative beat, timed to beat audio duration."""
    scenes: List[Dict] = []
    for beat_index, beat in enumerate(beats):
        duration_seconds = max(float(getattr(beat, "duration_seconds", 5.0) or 5.0), 3.0)
        scenes.append({
            "duration_seconds": duration_seconds,
            "beat_index": beat_index,
            "query_index": beat_index,
        })
    return scenes


def build_short_scene(duration_seconds: float) -> List[Dict]:
    short_duration = min(max(float(duration_seconds), 3.0), SHORT_MAX_DURATION_SECONDS)
    return [{"duration_seconds": short_duration, "beat_index": 0, "query_index": 0}]


def _pick_pexels_video_file_url(video_files: Sequence[dict]) -> Optional[str]:
    candidates = []
    for file_info in video_files or []:
        link = file_info.get("link")
        width = int(file_info.get("width") or 0)
        if link and width >= MIN_STOCK_VIDEO_WIDTH:
            candidates.append((width, link))
    if not candidates:
        for file_info in video_files or []:
            link = file_info.get("link")
            if link:
                return link
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[len(candidates) // 2][1]


def _search_pexels_video_url(query: str, orientation: str, result_index: int) -> Optional[str]:
    if not PEXELS_API_KEY:
        return None
    try:
        encoded_query = urllib.parse.quote(query[:100])
        url = (
            f"{PEXELS_VIDEOS_SEARCH_URL}?query={encoded_query}"
            f"&per_page=15&orientation={orientation}&size=medium"
        )
        request = urllib.request.Request(
            url,
            headers={"Authorization": PEXELS_API_KEY, "User-Agent": "ThulirBot/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            import json
            data = json.loads(response.read().decode("utf-8"))
        videos = data.get("videos", [])
        if not videos:
            return None
        chosen_video = videos[result_index % len(videos)]
        return _pick_pexels_video_file_url(chosen_video.get("video_files", []))
    except Exception as exc:
        log.warning("Pexels video search failed (%s): %s", query, exc)
        return None


def _download_stock_video_file(url: str, target_path: Path) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0"}, method="GET")
        with urllib.request.urlopen(request, timeout=120) as response:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(response.read())
        return target_path.exists() and target_path.stat().st_size > 50_000
    except Exception as exc:
        log.warning("Stock video download failed: %s", exc)
        return False


def _beat_search_query(beat, topic_title: str) -> str:
    beat_type = beat.beat_type.value if hasattr(beat.beat_type, "value") else str(beat.beat_type)
    keywords = list(getattr(beat, "visual_keywords", []) or [])
    return _build_query(keywords, topic_title, beat_type)


def fetch_beat_stock_videos(
    beats: Sequence,
    topic_title: str,
    output_dir: Path,
    orientation: str = "landscape",
) -> List[Path]:
    if not is_stock_video_enabled():
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    queries = [_beat_search_query(beat, topic_title) for beat in beats]
    if not queries:
        return []

    downloaded: List[Path] = []
    for scene_index, query in enumerate(queries):
        query_hash = hashlib.md5(f"{query}:{orientation}".encode()).hexdigest()[:10]
        target_path = output_dir / f"{orientation}_{scene_index}_{query_hash}.mp4"
        if target_path.exists() and target_path.stat().st_size > 50_000:
            downloaded.append(target_path)
            continue

        video_url = None
        for query_offset, candidate_query in enumerate(queries):
            video_url = _search_pexels_video_url(
                candidate_query,
                orientation,
                scene_index + query_offset,
            )
            if video_url:
                query = candidate_query
                break

        if not video_url:
            continue
        if _download_stock_video_file(video_url, target_path):
            downloaded.append(target_path)
            log.info(
                "Pexels video scene %d — %s (%s)",
                scene_index + 1,
                query,
                orientation,
            )

    log.info("%d stock videos fetched (%s)", len(downloaded), orientation)
    return downloaded


def probe_stock_video_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return max(float(result.stdout.strip()), 0.1)
    except ValueError:
        return 0.0


def validate_stock_video_clip(video_path: Optional[Path]) -> bool:
    if video_path is None or not video_path.exists():
        return False
    if video_path.stat().st_size < 50_000:
        return False
    return probe_stock_video_duration(video_path) > 0.0


def render_stock_scene(
    stock_video_path: Path,
    scene_duration_seconds: float,
    width: int,
    height: int,
    output_path: Path,
) -> bool:
    if not validate_stock_video_clip(stock_video_path):
        return False

    stock_duration = probe_stock_video_duration(stock_video_path)
    stream_loop = "-1" if stock_duration < scene_duration_seconds else "0"
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},eq=contrast=1.05:saturation=1.08"
    )
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-stream_loop", stream_loop,
        "-i", str(stock_video_path),
        "-t", f"{scene_duration_seconds:.3f}",
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-an", str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    return (
        result.returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 10_000
    )


def render_ken_burns_from_image(
    image_path: Path,
    scene_duration_seconds: float,
    width: int,
    height: int,
    output_path: Path,
    seed_index: int = 0,
) -> bool:
    if not image_path.exists():
        return False

    fps = 25
    frame_count = max(int(scene_duration_seconds * fps), fps * 3)
    pan_x = KB_PAN_RIGHT if seed_index % 2 == 0 else "iw/2-(iw/zoom/2)-on*0.3"
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{KB_ZOOM_IN}':x='{pan_x}':y='{KB_PAN_CENTER}':"
        f"d={frame_count}:fps={fps}:s={width}x{height}"
    )
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image_path),
        "-t", f"{scene_duration_seconds:.3f}",
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-an", str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    return (
        result.returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 10_000
    )


def build_stock_silent_video(
    scenes: Sequence[Dict],
    stock_videos: Sequence[Path],
    fallback_image_paths: Sequence[Path],
    width: int,
    height: int,
    output_path: Path,
    output_name: str,
) -> bool:
    if not scenes or not fallback_image_paths:
        return False

    temp_dir = output_path.parent
    scene_clips: List[Path] = []
    for scene_index, scene in enumerate(scenes):
        clip_path = temp_dir / f"{output_name}_stock_scene_{scene_index}.mp4"
        stock_path = stock_videos[scene_index] if scene_index < len(stock_videos) else None
        rendered = False
        if stock_path and validate_stock_video_clip(stock_path):
            rendered = render_stock_scene(
                stock_path,
                scene["duration_seconds"],
                width,
                height,
                clip_path,
            )
        if not rendered:
            fallback_image = fallback_image_paths[scene_index % len(fallback_image_paths)]
            rendered = render_ken_burns_from_image(
                fallback_image,
                scene["duration_seconds"],
                width,
                height,
                clip_path,
                seed_index=scene_index,
            )
        if not rendered:
            log.error("Failed to render stock scene %d", scene_index + 1)
            return False
        scene_clips.append(clip_path)

    concat_list_path = temp_dir / f"{output_name}_stock_concat.txt"
    with concat_list_path.open("w", encoding="utf-8") as handle:
        for clip_path in scene_clips:
            handle.write(f"file '{clip_path}'\n")

    concat_result = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", str(output_path),
    ], capture_output=True, text=True, timeout=300)

    for temp_path in scene_clips + [concat_list_path]:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

    return (
        concat_result.returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 10_000
    )


def encode_intro_video(intro_frames, output_path: Path, fps: int) -> bool:
    if not intro_frames:
        return False

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", "1920x1080", "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "pipe:0",
        "-vf", "fps=24",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for frame in intro_frames:
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    return_code = process.wait()
    return return_code == 0 and output_path.exists()


def concat_video_segments(segment_paths: Sequence[Path], output_path: Path) -> bool:
    existing_segments = [path for path in segment_paths if path.exists()]
    if not existing_segments:
        return False

    concat_list_path = output_path.parent / f"{output_path.stem}_concat.txt"
    with concat_list_path.open("w", encoding="utf-8") as handle:
        for segment_path in existing_segments:
            handle.write(f"file '{segment_path}'\n")

    result = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", str(output_path),
    ], capture_output=True, text=True, timeout=300)

    try:
        concat_list_path.unlink(missing_ok=True)
    except OSError:
        pass

    return result.returncode == 0 and output_path.exists()


def mux_audio_into_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    max_duration_seconds: Optional[float] = None,
) -> bool:
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    if max_duration_seconds is not None:
        command[command.index("-shortest")] = "-t"
        command.insert(command.index("-t") + 1, f"{max_duration_seconds:.3f}")
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    return result.returncode == 0 and output_path.exists()
