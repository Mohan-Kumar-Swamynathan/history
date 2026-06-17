"""Optional CC0 Lottie renderer — falls back to colored SVG icons."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image

from src.core.config_loader import PROJECT_ROOT

LOTTIE_DIR = PROJECT_ROOT / "assets" / "lottie"


def render_lottie_frame(icon_name: str, progress: float, size: int = 180) -> Optional[Image.Image]:
    """Render a Lottie animation frame if assets exist; otherwise return None."""
    lottie_path = LOTTIE_DIR / f"{icon_name}.json"
    if not lottie_path.exists():
        return None
    try:
        from lottie import exporters, parsers  # type: ignore[import-untyped]
    except ImportError:
        return None

    try:
        animation = parsers.tgs.parse_tgs(lottie_path.read_bytes())
        frame_index = int(progress * animation.out_point)
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        exporters.export_png(animation, image, frame=frame_index)
        return image
    except Exception:
        return None
