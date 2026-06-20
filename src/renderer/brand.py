"""Thulir (துளிர்) channel branding — exact colors from channel icon & banner.

Extracted from:
  - channels4_profile.jpg : dark olive-green text on warm cream bg
  - channels4_banner.jpg  : deep forest green brush stroke + warm cream sky + bright leaf sprout

Color analysis results:
  Left brush stroke RGB:  [29, 48, 16]   → #1d3010
  Icon text green  RGB:   [29, 51, 11]   → #1d330b
  Mid green        RGB:   [81, 117, 18]  → #517512
  Bright leaf      RGB:   [114, 140, 15] → #728c0f
  Warm cream BG    RGB:   [244, 235, 191]→ #f4ebBF
"""

# ── Exact brand colors ────────────────────────────────────────────────
BRAND_PRIMARY_HEX   = "#1D3010"   # deep forest green (banner brush stroke)
BRAND_DARK_HEX      = "#1D330B"   # darkest green (thuLir lettering)
BRAND_MID_HEX       = "#517512"   # mid green (leaves, accents)
BRAND_LEAF_HEX      = "#728C0F"   # bright olive-green (sprout)
BRAND_CREAM_HEX     = "#F4EBBF"   # warm cream (banner sky background)
BRAND_LIGHT_HEX     = "#EDF7E0"   # very light green tint (video bg wash)
BRAND_WHITE_HEX     = "#FAFAF0"   # off-white with warm tint (video bg)
BRAND_GOLD_HEX      = "#D4AF37"   # gold accent (highlight word, CTA)
BRAND_INK_HEX       = "#1A2E08"   # near-black green ink (body text)
BRAND_GREY_HEX      = "#6B7C4A"   # muted olive-grey (faded/spoken text)

def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

PRIMARY   = _hex(BRAND_PRIMARY_HEX)   # (29, 48, 16)
DARK      = _hex(BRAND_DARK_HEX)      # (29, 51, 11)
MID       = _hex(BRAND_MID_HEX)       # (81, 117, 18)
LEAF      = _hex(BRAND_LEAF_HEX)      # (114, 140, 15)
CREAM     = _hex(BRAND_CREAM_HEX)     # (244, 235, 191)
LIGHT     = _hex(BRAND_LIGHT_HEX)     # (237, 247, 224)
BG        = _hex(BRAND_WHITE_HEX)     # (250, 250, 240)
ACCENT    = _hex(BRAND_GOLD_HEX)      # (212, 175, 55)
INK       = _hex(BRAND_INK_HEX)       # (26, 46, 8)
GREY      = _hex(BRAND_GREY_HEX)      # (107, 124, 74)
WHITE     = (255, 255, 255)
RED       = ACCENT                    # use gold instead of red for highlights
SECONDARY = LEAF
DIVIDER   = LIGHT

# Intro / lower-third config
INTRO_DURATION_S  = 3.5
INTRO_FPS         = 12
INTRO_FRAMES      = int(INTRO_DURATION_S * INTRO_FPS)   # 42
LOWER_THIRD_H     = 80
