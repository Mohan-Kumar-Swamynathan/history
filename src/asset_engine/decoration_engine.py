"""Keyword-matched colored icons and scene decorations — 100% free."""

from __future__ import annotations

import io
import math
import re
import sys
from pathlib import Path
from typing import List, Tuple

import cairosvg
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from icon_library import get_icon_paths, pick_icon_for_text  # noqa: E402
from src.core.config_loader import CONFIG_DIR, get_output_dir
from src.asset_engine.lottie_renderer import render_lottie_frame
from src.core.models import ScenePlan

import yaml

_ICON_COLORS: dict | None = None
_PALETTES: dict | None = None
_ICON_CACHE_DIR = get_output_dir() / "cache" / "icons"


def _load_colors() -> tuple[dict, dict]:
    global _ICON_COLORS, _PALETTES
    if _ICON_COLORS is None:
        path = CONFIG_DIR / "colors.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        _PALETTES = data.get("palettes", {})
        _ICON_COLORS = data.get("icon_colors", {})
    return _PALETTES or {}, _ICON_COLORS or {}


def get_emotion_palette(emotion: str) -> dict:
    palettes, _ = _load_colors()
    return palettes.get(emotion, palettes.get("neutral", {
        "wash": [248, 248, 245],
        "accent": [80, 80, 80],
        "icon": [40, 40, 40],
        "glow": [220, 220, 215],
    }))


def pick_scene_icons(text: str, hero_icon: str | None = None, max_icons: int = 1) -> List[str]:
    if hero_icon:
        return [hero_icon]
    icon = pick_icon_for_text(text)
    if icon:
        return [icon]
    defaults = ["lightbulb", "star", "heart"]
    return [defaults[len(text) % len(defaults)]]


def get_icon_color(icon_name: str) -> Tuple[int, int, int]:
    _, icon_colors = _load_colors()
    rgb = icon_colors.get(icon_name, icon_colors.get("default", [205, 35, 25]))
    return tuple(rgb)


def render_colored_icon(
    icon_name: str,
    progress: float,
    size: int = 180,
    fill: bool = True,
) -> Image.Image:
    bucket = round(progress * 20) / 20
    cache_key = f"{icon_name}_{size}_{bucket:.2f}"
    cache_path = _ICON_CACHE_DIR / f"{cache_key}.png"
    if cache_path.exists():
        return Image.open(cache_path).convert("RGBA")

    paths = get_icon_paths(icon_name)
    color_rgb = get_icon_color(icon_name)
    stroke = f"rgb({color_rgb[0]},{color_rgb[1]},{color_rgb[2]})"
    fill_color = stroke if fill else "none"
    path_count = len(paths)
    drawn = bucket * path_count
    parts: List[str] = []

    for index, (path_data, stroke_width) in enumerate(paths):
        length = max(60.0, len(re.findall(r"-?[\d.]+", path_data)) // 2 * 14.0)
        local_progress = min(1.0, max(0.0, drawn - index))
        dash = length * local_progress
        gap = length - dash + 1
        thick = stroke_width * 1.4
        parts.append(
            f'<path d="{path_data}" fill="{fill_color}" fill-opacity="0.15" '
            f'stroke="{stroke}" stroke-width="{thick:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{gap:.1f}"/>'
        )

    svg = (
        f'<svg width="{size}" height="{size}" viewBox="0 0 120 120" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'
    )
    image = Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    )).convert("RGBA")
    _ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(cache_path)
    return image


def _placement_coords(placement: str, width: int, height: int, icon_size: int) -> Tuple[int, int]:
    margin = 80
    if placement == "top_right":
        return width - icon_size - margin, margin
    if placement == "bottom_center":
        return (width - icon_size) // 2, height - icon_size - margin
    if placement == "left_margin":
        return margin, int(height * 0.55)
    return margin, int(height * 0.65)


def composite_scene_decorations(
    base_frame: Image.Image,
    scene_text: str,
    emotion: str,
    progress: float,
    frame_index: int,
    scene_plan: ScenePlan | None = None,
) -> Image.Image:
    palette = get_emotion_palette(emotion)
    canvas = base_frame.copy().convert("RGBA")
    width, height = canvas.size

    wash = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wash_draw = ImageDraw.Draw(wash)
    wash_rgb = palette.get("wash", [248, 248, 245])
    glow_rgb = palette.get("glow", [220, 220, 215])
    accent_rgb = palette.get("accent", [80, 80, 80])

    wash_draw.ellipse([-80, -60, width // 2, height // 2], fill=(*wash_rgb, 35))
    wash_draw.ellipse([width // 3, height // 2, width, height + 40], fill=(*glow_rgb, 25))
    canvas = Image.alpha_composite(canvas, wash)

    hero_icon = scene_plan.hero_icon if scene_plan else None
    placement = scene_plan.icon_placement if scene_plan else "bottom_left"
    icons = pick_scene_icons(scene_text, hero_icon=hero_icon, max_icons=1)

    for slot_index, icon_name in enumerate(icons):
        bob = int(math.sin((progress * 6 + slot_index) * math.pi) * 10)
        pulse = 1.0 + 0.05 * math.sin((progress * 8 + frame_index * 0.15) * math.pi)
        icon_size = int(160 * pulse)
        icon_progress = min(1.0, progress * 1.2)
        if icon_progress <= 0:
            continue

        icon_img = render_lottie_frame(icon_name, icon_progress, size=icon_size)
        if icon_img is None:
            icon_img = render_colored_icon(icon_name, icon_progress, size=icon_size)
        base_x, base_y = _placement_coords(placement, width, height, icon_size)
        paste_x = base_x
        paste_y = base_y + bob

        glow = Image.new("RGBA", (icon_size + 40, icon_size + 40), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([10, 10, icon_size + 30, icon_size + 30], fill=(*accent_rgb, 40))
        canvas.paste(glow, (paste_x - 20, paste_y - 20), glow)
        canvas.paste(icon_img, (paste_x, paste_y), icon_img)

    return canvas.convert("RGB")
