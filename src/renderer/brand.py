"""Thulir channel branding — single source of truth.

To update colors: change BRAND_PRIMARY and BRAND_SECONDARY here only.
All renderers import from this file.

Current: deep forest green theme.
Update BRAND_PRIMARY hex if channel icon uses a different shade.
"""

# ── Primary brand color (channel green) ──────────────────────────────
# Derived from channel icon — update this if the exact shade is different
BRAND_PRIMARY_HEX   = "#2D6A4F"   # deep forest green
BRAND_SECONDARY_HEX = "#95D5B2"   # light mint green (accent)
BRAND_DARK_HEX      = "#1B4332"   # dark green (headings, strong text)
BRAND_LIGHT_HEX     = "#D8F3DC"   # very light green (background tint)
BRAND_WHITE         = "#FAFFF8"   # off-white with green tint (video bg)
BRAND_INK           = "#12231A"   # near-black with green tint (body text)
BRAND_ACCENT        = "#FFB703"   # warm gold (highlight word, CTA)
BRAND_GREY          = "#6B8F71"   # muted green-grey (spoken/faded text)

# RGB tuples for PIL
def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

PRIMARY   = _hex(BRAND_PRIMARY_HEX)    # (45, 106, 79)
SECONDARY = _hex(BRAND_SECONDARY_HEX)  # (149, 213, 178)
DARK      = _hex(BRAND_DARK_HEX)       # (27, 67, 50)
LIGHT     = _hex(BRAND_LIGHT_HEX)      # (216, 243, 220)
BG        = _hex(BRAND_WHITE)          # (250, 255, 248)
INK       = _hex(BRAND_INK)            # (18, 35, 26)
ACCENT    = _hex(BRAND_ACCENT)         # (255, 183, 3)
GREY      = _hex(BRAND_GREY)           # (107, 143, 113)
RED       = (205, 35, 25)              # keep for error/highlight
WHITE     = (255, 255, 255)

# Intro card dimensions
INTRO_DURATION_S  = 3.5    # seconds
INTRO_FPS         = 12
INTRO_FRAMES      = int(INTRO_DURATION_S * INTRO_FPS)  # 42 frames

# Lower-third strip
LOWER_THIRD_H     = 80     # px height of bottom branding strip
