"""Thumbnail generation — hook frame + 2-4 word CTR text."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from src.core.config_loader import resolve_font_path
from src.core.models import TopicCandidate

EMOTION_COLORS = {
    "surprise": (205, 35, 25),
    "shock": (180, 20, 20),
    "hope": (34, 120, 60),
    "empathy": (80, 80, 140),
    "excitement": (205, 35, 25),
}


class ThumbnailGenerator:
    def generate(
        self,
        topic: TopicCandidate,
        output_path: Path,
        hook_frame: Optional[np.ndarray] = None,
        thumbnail_text: str = "",
        emotion_trigger: str = "surprise",
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if hook_frame is not None:
            image = Image.fromarray(hook_frame).resize((1280, 720), Image.Resampling.LANCZOS)
            image = ImageEnhance.Contrast(image).enhance(1.2)
            image = ImageEnhance.Brightness(image).enhance(0.92)
        else:
            image = Image.new("RGB", (1280, 720), (248, 248, 245))

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([0, 400, 1280, 720], fill=(0, 0, 0, 120))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(image)
        title = thumbnail_text or " ".join(topic.title_ta.split()[:4])
        font_path = resolve_font_path("ta_black")
        font = ImageFont.truetype(font_path, 88) if font_path else ImageFont.load_default()
        bbox = draw.textbbox((0, 0), title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (1280 - text_width) / 2
        text_y = 720 - text_height - 60
        accent = EMOTION_COLORS.get(emotion_trigger, (205, 35, 25))
        draw.rectangle(
            [text_x - 24, text_y - 20, text_x + text_width + 24, text_y + text_height + 20],
            fill=(255, 255, 255),
        )
        draw.text((text_x, text_y), title, font=font, fill=(15, 15, 15))
        draw.rectangle([24, 24, 1256, 696], outline=accent, width=10)
        image.save(output_path, "JPEG", quality=92)
        return output_path

    def pick_hook_frame(self, frames: List[np.ndarray], progress: float = 0.8) -> Optional[np.ndarray]:
        if not frames:
            return None
        index = min(len(frames) - 1, int(len(frames) * progress))
        return frames[index]
