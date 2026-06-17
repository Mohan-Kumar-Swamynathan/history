#!/usr/bin/env python3
"""Pexels stock video client for background footage."""

import hashlib
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PEXELS_CACHE_DIR = Path(__file__).parent / "cache" / "pexels"

HOOK_SEARCH_TERMS = {
    "mystery": "ancient temple India history",
    "architecture": "Indian temple architecture stone",
    "rebellion": "historical battle India soldiers",
    "literature": "ancient manuscript scroll India",
    "trade": "ancient port ships India ocean",
    "temple": "Hindu temple India ancient",
    "conflict": "historical war India fort",
    "empire": "ancient kingdom India palace",
    "tragedy": "historical famine India village",
    "emotion": "Tamil culture heritage India",
    "engineering": "ancient engineering India water",
    "culture": "Indian classical dance heritage",
}


def build_search_query(topic_info: Dict) -> str:
    hook = topic_info.get("hook", "mystery")
    base = HOOK_SEARCH_TERMS.get(hook, "Tamil history India ancient")
    era = topic_info.get("era", "")
    era_en = re.sub(r"[^\w\s]", "", era)
    return f"{base} {era_en}".strip()


def _pexels_get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY}, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _pick_best_video_file(video_files: List[dict]) -> dict:
    landscape = [
        vf for vf in video_files
        if vf.get("width", 0) >= vf.get("height", 0) and vf.get("width", 0) >= 1280
    ]
    candidates = landscape or video_files
    return max(candidates, key=lambda vf: vf.get("width", 0))


def _download_clip(download_url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(download_url, method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())
    return destination


def fetch_stock_clips(topic_info: Dict, count: int = 3) -> List[Path]:
    if not PEXELS_API_KEY:
        log.warning("PEXELS_API_KEY not set — skipping stock footage")
        return []

    query = build_search_query(topic_info)
    query_hash = hashlib.md5(query.encode()).hexdigest()[:10]
    cache_marker = PEXELS_CACHE_DIR / f"{query_hash}_manifest.json"

    if cache_marker.exists():
        manifest = json.loads(cache_marker.read_text("utf-8"))
        cached = [Path(p) for p in manifest.get("clips", []) if Path(p).exists()]
        if cached:
            log.info(f"Pexels cache hit: {len(cached)} clips")
            return cached[:count]

    try:
        url = f"{PEXELS_SEARCH_URL}?query={urllib.request.quote(query)}&per_page={count + 2}&orientation=landscape"
        data = _pexels_get(url)
    except Exception as exc:
        log.warning(f"Pexels search failed: {exc}")
        return []

    videos = data.get("videos", [])
    if not videos:
        log.warning(f"No Pexels results for query: {query}")
        return []

    downloaded: List[Path] = []
    for index, video in enumerate(videos[:count]):
        video_files = video.get("video_files", [])
        if not video_files:
            continue
        best_file = _pick_best_video_file(video_files)
        clip_path = PEXELS_CACHE_DIR / f"{query_hash}_{index}.mp4"
        try:
            _download_clip(best_file["link"], clip_path)
            downloaded.append(clip_path)
            log.info(f"Downloaded Pexels clip {index + 1}: {clip_path.name}")
        except Exception as exc:
            log.warning(f"Failed to download clip {index + 1}: {exc}")

    if downloaded:
        cache_marker.write_text(
            json.dumps({"query": query, "clips": [str(p) for p in downloaded]}, indent=2),
            encoding="utf-8",
        )
    return downloaded
