#!/usr/bin/env python3
"""Single entry point — துளிர் Tamil storytelling channel."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.generate_video import VideoPipeline  # noqa: E402


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="துளிர் — Tamil storytelling video generator")
    parser.add_argument("--category", default="storytelling", help="Content category")
    parser.add_argument("--topic", default="", help="Manual Tamil topic override")
    parser.add_argument("--voice", default="default", choices=["default", "female"])
    parser.add_argument("--format", default="long", choices=["long", "short"], help="Video format")
    parser.add_argument(
        "--daily-slot",
        default="",
        choices=["", "morning_long", "morning_short", "evening_long", "evening_short"],
        help="Daily content slot",
    )
    parser.add_argument("--no-shorts", action="store_true", help="Skip Shorts generation on long runs")
    parser.add_argument("--skip-upload", action="store_true", default=True)
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube")
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    args = build_argument_parser().parse_args()
    skip_upload = not args.upload

    pipeline = VideoPipeline(voice_key=args.voice)
    package = pipeline.run(
        category=args.category,
        topic_override=args.topic or None,
        skip_upload=skip_upload,
        video_format=args.format,
        daily_slot=args.daily_slot or None,
        include_shorts=not args.no_shorts,
    )

    print("\n✅ Video generated successfully")
    print(f"   Run ID:   {package.run_id}")
    print(f"   Format:   {package.format}")
    print(f"   Topic:    {package.topic.title_ta}")
    if package.format == "long":
        print(f"   Video:    {package.long_video_path}")
    if package.shorts_video_path:
        print(f"   Shorts:   {package.shorts_video_path}")
    print(f"   Thumb:    {package.thumbnail_path}")
    if package.metadata:
        print(f"   Title:    {package.metadata.title_ta}")
    print(f"   SRT:      {package.srt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
