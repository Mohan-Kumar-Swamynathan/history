"""Tint scene backgrounds with emotion-based color fills."""

from __future__ import annotations

from typing import Callable

# Emotion → (primary fill hex, secondary fill hex)
BACKGROUND_TINTS = {
    "money": ("#FFF8E1", "#FFD54F"),
    "office": ("#ECEFF1", "#90A4AE"),
    "phone": ("#E3F2FD", "#64B5F6"),
    "home": ("#FFF3E0", "#FFB74D"),
    "think": ("#F3E5F5", "#BA68C8"),
    "trophy": ("#FFFDE7", "#FFD54F"),
    "heart_break": ("#FCE4EC", "#F48FB1"),
    "path_up": ("#E8F5E9", "#81C784"),
    "clean": ("#FAFAFA", "#EEEEEE"),
}


def wrap_background_with_color(draw_fn: Callable, tint_key: str) -> Callable:
    """Wrap an ae_engine background SVG function with colored fills."""
    primary, secondary = BACKGROUND_TINTS.get(tint_key, BACKGROUND_TINTS["clean"])

    def colored_draw(color: str = "#161616") -> str:
        inner = draw_fn(color)
        return (
            f'<rect x="0" y="0" width="600" height="500" fill="{primary}" rx="12"/>'
            f'<rect x="40" y="300" width="520" height="160" fill="{secondary}" '
            f'opacity="0.35" rx="8"/>'
            f"{inner}"
        )

    return colored_draw


def tint_key_from_background(background_key: str | None) -> str:
    if not background_key:
        return "clean"
    return background_key if background_key in BACKGROUND_TINTS else "clean"
