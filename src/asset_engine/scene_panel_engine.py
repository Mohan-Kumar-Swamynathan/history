"""Scene panel engine — illustrated contextual panels for the right side of the frame.

Each beat gets a full illustrated panel (600×700 px) built from layered SVG components:
  - Background environment (office, street, factory, kitchen, etc.)
  - Foreground props animated in (briefcase, phone, coins, clock, etc.)
  - Optional data overlay (number callout, timeline bar, stat badge)
  - Keyword-matched from beat narration + visual_keywords

Panel draws itself over the scene duration (pencil-draw reveal effect),
matching the whiteboard style of the left-side text.
"""

from __future__ import annotations

import io
import math
import random
import re
from typing import Optional

import cairosvg
from PIL import Image, ImageDraw, ImageFont

# Panel canvas
PW, PH = 640, 680
INK  = "#1a1a1a"
RED  = "#CD2319"
GOLD = "#D4A017"
GREY = "#AAAAAA"

# ── Environment backgrounds ──────────────────────────────────────────

def _env_office() -> str:
    return f"""
    <!-- floor -->
    <rect x="0" y="520" width="{PW}" height="160" fill="#F5F0E8" rx="0"/>
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="520" fill="#FAFAF7" rx="0"/>
    <!-- desk -->
    <rect x="80" y="380" width="480" height="18" rx="4" fill="none" stroke="{INK}" stroke-width="5"/>
    <rect x="100" y="398" width="12" height="120" rx="3" fill="none" stroke="{INK}" stroke-width="3"/>
    <rect x="528" y="398" width="12" height="120" rx="3" fill="none" stroke="{INK}" stroke-width="3"/>
    <!-- monitor -->
    <rect x="240" y="240" width="200" height="140" rx="8" fill="none" stroke="{INK}" stroke-width="4"/>
    <rect x="260" y="258" width="160" height="100" rx="4" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="4 3" opacity="0.4"/>
    <line x1="340" y1="380" x2="340" y2="395" stroke="{INK}" stroke-width="4"/>
    <line x1="310" y1="395" x2="370" y2="395" stroke="{INK}" stroke-width="3"/>
    <!-- window -->
    <rect x="420" y="80" width="160" height="200" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="500" y1="80" x2="500" y2="280" stroke="{INK}" stroke-width="2"/>
    <line x1="420" y1="180" x2="580" y2="180" stroke="{INK}" stroke-width="2"/>
    <!-- papers on desk -->
    <rect x="100" y="356" width="110" height="24" rx="3" fill="none" stroke="{INK}" stroke-width="2.5" opacity="0.6"/>
    <line x1="110" y1="364" x2="198" y2="364" stroke="{INK}" stroke-width="1.5" opacity="0.5"/>
    <line x1="110" y1="372" x2="185" y2="372" stroke="{INK}" stroke-width="1.5" opacity="0.5"/>
    """

def _env_street() -> str:
    return f"""
    <!-- sky -->
    <rect x="0" y="0" width="{PW}" height="380" fill="#FAFAF7"/>
    <!-- road -->
    <rect x="0" y="380" width="{PW}" height="300" fill="#F0EDE5"/>
    <!-- road marking -->
    <line x1="0" y1="460" x2="{PW}" y2="460" stroke="{INK}" stroke-width="2" stroke-dasharray="40 20" opacity="0.3"/>
    <!-- buildings left -->
    <rect x="20" y="120" width="140" height="260" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <rect x="40" y="145" width="35" height="40" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <rect x="90" y="145" width="35" height="40" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <rect x="40" y="205" width="35" height="40" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <rect x="90" y="205" width="35" height="40" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <!-- building right -->
    <rect x="460" y="80" width="160" height="300" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <rect x="475" y="105" width="30" height="35" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <rect x="520" y="105" width="30" height="35" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <rect x="565" y="105" width="30" height="35" rx="2" fill="none" stroke="{INK}" stroke-width="2" opacity="0.6"/>
    <!-- streetlamp -->
    <line x1="320" y1="180" x2="320" y2="420" stroke="{INK}" stroke-width="4"/>
    <path d="M 320 180 Q 360 160 370 190" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <circle cx="370" cy="192" r="10" fill="none" stroke="{GOLD}" stroke-width="3"/>
    """

def _env_kitchen() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- counter -->
    <rect x="40" y="360" width="560" height="22" rx="4" fill="none" stroke="{INK}" stroke-width="5"/>
    <rect x="40" y="382" width="560" height="160" rx="0" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <!-- cabinet top -->
    <rect x="60" y="80" width="200" height="160" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="160" y1="80" x2="160" y2="240" stroke="{INK}" stroke-width="2.5"/>
    <!-- cabinet right -->
    <rect x="380" y="80" width="220" height="160" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="490" y1="80" x2="490" y2="240" stroke="{INK}" stroke-width="2.5"/>
    <!-- stove -->
    <rect x="180" y="300" width="140" height="60" rx="6" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <circle cx="215" cy="330" r="18" fill="none" stroke="{INK}" stroke-width="3"/>
    <circle cx="285" cy="330" r="18" fill="none" stroke="{INK}" stroke-width="3"/>
    """

def _env_factory() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#F8F6F0"/>
    <!-- floor -->
    <rect x="0" y="480" width="{PW}" height="200" fill="#F2EDE0"/>
    <line x1="0" y1="480" x2="{PW}" y2="480" stroke="{INK}" stroke-width="3"/>
    <!-- conveyor belt -->
    <rect x="60" y="400" width="520" height="30" rx="8" fill="none" stroke="{INK}" stroke-width="4"/>
    <line x1="80" y1="415" x2="560" y2="415" stroke="{INK}" stroke-width="2" stroke-dasharray="30 15" opacity="0.5"/>
    <!-- machine left -->
    <rect x="60" y="200" width="120" height="200" rx="6" fill="none" stroke="{INK}" stroke-width="4"/>
    <circle cx="120" cy="260" r="35" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="120" y1="225" x2="120" y2="295" stroke="{INK}" stroke-width="3"/>
    <line x1="85" y1="260" x2="155" y2="260" stroke="{INK}" stroke-width="3"/>
    <!-- machine right -->
    <rect x="460" y="180" width="140" height="220" rx="6" fill="none" stroke="{INK}" stroke-width="4"/>
    <rect x="475" y="200" width="110" height="80" rx="4" fill="none" stroke="{INK}" stroke-width="2.5" opacity="0.5"/>
    <line x1="530" y1="320" x2="530" y2="400" stroke="{INK}" stroke-width="4"/>
    """

def _env_home() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- floor -->
    <rect x="0" y="500" width="{PW}" height="180" fill="#F5F0E5"/>
    <line x1="0" y1="500" x2="{PW}" y2="500" stroke="{INK}" stroke-width="3"/>
    <!-- sofa -->
    <rect x="100" y="400" width="380" height="100" rx="12" fill="none" stroke="{INK}" stroke-width="4"/>
    <rect x="100" y="360" width="60" height="140" rx="10" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <rect x="420" y="360" width="60" height="140" rx="10" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="160" y1="400" x2="420" y2="400" stroke="{INK}" stroke-width="2.5" opacity="0.5"/>
    <!-- picture frame -->
    <rect x="240" y="80" width="200" height="140" rx="6" fill="none" stroke="{INK}" stroke-width="4"/>
    <line x1="260" y1="100" x2="420" y2="200" stroke="{INK}" stroke-width="1.5" opacity="0.3"/>
    <line x1="420" y1="100" x2="260" y2="200" stroke="{INK}" stroke-width="1.5" opacity="0.3"/>
    <!-- lamp -->
    <line x1="520" y1="280" x2="520" y2="500" stroke="{INK}" stroke-width="3.5"/>
    <path d="M 490 200 Q 520 160 550 200 L 540 280 L 500 280 Z" fill="none" stroke="{INK}" stroke-width="3"/>
    """

def _env_restaurant() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- floor -->
    <rect x="0" y="480" width="{PW}" height="200" fill="#F0EBE0"/>
    <line x1="0" y1="480" x2="{PW}" y2="480" stroke="{INK}" stroke-width="3"/>
    <!-- table -->
    <ellipse cx="320" cy="420" rx="180" ry="40" fill="none" stroke="{INK}" stroke-width="4.5"/>
    <line x1="200" y1="420" x2="180" y2="560" stroke="{INK}" stroke-width="4"/>
    <line x1="440" y1="420" x2="460" y2="560" stroke="{INK}" stroke-width="4"/>
    <!-- plate left -->
    <circle cx="220" cy="400" r="45" fill="none" stroke="{INK}" stroke-width="3"/>
    <circle cx="220" cy="400" r="32" fill="none" stroke="{INK}" stroke-width="1.5" opacity="0.4"/>
    <!-- plate right -->
    <circle cx="420" cy="400" r="45" fill="none" stroke="{INK}" stroke-width="3"/>
    <circle cx="420" cy="400" r="32" fill="none" stroke="{INK}" stroke-width="1.5" opacity="0.4"/>
    <!-- candle center -->
    <rect x="308" y="340" width="24" height="60" rx="4" fill="none" stroke="{INK}" stroke-width="3"/>
    <path d="M 315 330 Q 320 310 325 330" fill="none" stroke="{GOLD}" stroke-width="3"/>
    <!-- window with curtains -->
    <rect x="80" y="60" width="160" height="200" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <path d="M 80 60 Q 120 140 80 260" fill="none" stroke="{INK}" stroke-width="3" opacity="0.6"/>
    <path d="M 240 60 Q 200 140 240 260" fill="none" stroke="{INK}" stroke-width="3" opacity="0.6"/>
    """

def _env_library() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- bookshelves -->
    <rect x="20" y="40" width="200" height="560" rx="4" fill="none" stroke="{INK}" stroke-width="4"/>
    <line x1="20" y1="150" x2="220" y2="150" stroke="{INK}" stroke-width="3"/>
    <line x1="20" y1="270" x2="220" y2="270" stroke="{INK}" stroke-width="3"/>
    <line x1="20" y1="390" x2="220" y2="390" stroke="{INK}" stroke-width="3"/>
    <line x1="20" y1="510" x2="220" y2="510" stroke="{INK}" stroke-width="3"/>
    <!-- books row 1 -->
    <rect x="30" y="60" width="22" height="82" rx="2" fill="none" stroke="{INK}" stroke-width="2.5"/>
    <rect x="56" y="68" width="18" height="74" rx="2" fill="none" stroke="{INK}" stroke-width="2.5"/>
    <rect x="78" y="55" width="26" height="87" rx="2" fill="none" stroke="{INK}" stroke-width="2.5"/>
    <rect x="108" y="65" width="20" height="77" rx="2" fill="none" stroke="{INK}" stroke-width="2.5"/>
    <rect x="132" y="58" width="24" height="84" rx="2" fill="none" stroke="{INK}" stroke-width="2.5"/>
    <!-- reading table -->
    <rect x="280" y="360" width="320" height="16" rx="4" fill="none" stroke="{INK}" stroke-width="4.5"/>
    <line x1="300" y1="376" x2="290" y2="500" stroke="{INK}" stroke-width="4"/>
    <line x1="560" y1="376" x2="570" y2="500" stroke="{INK}" stroke-width="4"/>
    <!-- open book on table -->
    <path d="M 300 340 Q 440 300 580 340 L 580 370 Q 440 340 300 370 Z" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="440" y1="305" x2="440" y2="370" stroke="{INK}" stroke-width="2.5"/>
    """

def _env_jail() -> str:
    return f"""
    <!-- wall dark -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#F5F2EC"/>
    <!-- floor -->
    <rect x="0" y="500" width="{PW}" height="180" fill="#EDEAD8"/>
    <line x1="0" y1="500" x2="{PW}" y2="500" stroke="{INK}" stroke-width="3"/>
    <!-- bars -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="none" stroke="{INK}" stroke-width="2" opacity="0.1"/>
    <line x1="80" y1="0" x2="80" y2="520" stroke="{INK}" stroke-width="8"/>
    <line x1="175" y1="0" x2="175" y2="520" stroke="{INK}" stroke-width="8"/>
    <line x1="270" y1="0" x2="270" y2="520" stroke="{INK}" stroke-width="8"/>
    <line x1="365" y1="0" x2="365" y2="520" stroke="{INK}" stroke-width="8"/>
    <line x1="460" y1="0" x2="460" y2="520" stroke="{INK}" stroke-width="8"/>
    <line x1="555" y1="0" x2="555" y2="520" stroke="{INK}" stroke-width="8"/>
    <!-- horizontal bars -->
    <line x1="0" y1="180" x2="{PW}" y2="180" stroke="{INK}" stroke-width="6"/>
    <line x1="0" y1="360" x2="{PW}" y2="360" stroke="{INK}" stroke-width="6"/>
    <!-- bench -->
    <rect x="100" y="440" width="340" height="16" rx="4" fill="none" stroke="{INK}" stroke-width="4"/>
    """

def _env_mountain() -> str:
    return f"""
    <!-- sky -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- mountain range back -->
    <polygon points="0,480 160,160 320,380 480,120 640,400 640,480"
             fill="none" stroke="{INK}" stroke-width="3" opacity="0.4"/>
    <!-- mountain main -->
    <polygon points="100,520 320,80 540,520"
             fill="none" stroke="{INK}" stroke-width="5"/>
    <!-- snow cap -->
    <polygon points="280,130 320,80 360,130 340,145 300,145"
             fill="none" stroke="{INK}" stroke-width="3.5"/>
    <!-- path up mountain -->
    <path d="M 120 520 Q 200 480 240 420 Q 290 360 310 280"
          fill="none" stroke="{INK}" stroke-width="3" stroke-dasharray="15 10"/>
    <!-- flag at top -->
    <line x1="320" y1="80" x2="320" y2="30" stroke="{INK}" stroke-width="3"/>
    <polygon points="320,30 360,48 320,66" fill="none" stroke="{RED}" stroke-width="2.5"/>
    <!-- clouds -->
    <path d="M 440 120 Q 460 100 490 110 Q 510 95 535 108 Q 555 100 570 115 Q 560 130 530 128 Q 510 140 490 130 Q 465 140 440 120"
          fill="none" stroke="{INK}" stroke-width="2.5" opacity="0.5"/>
    """

def _env_courtroom() -> str:
    return f"""
    <!-- wall -->
    <rect x="0" y="0" width="{PW}" height="{PH}" fill="#FAFAF7"/>
    <!-- judge bench -->
    <rect x="120" y="80" width="400" height="28" rx="4" fill="none" stroke="{INK}" stroke-width="5"/>
    <rect x="120" y="108" width="400" height="160" rx="4" fill="none" stroke="{INK}" stroke-width="4"/>
    <!-- gavel -->
    <rect x="260" y="50" width="120" height="30" rx="8" fill="none" stroke="{INK}" stroke-width="4"/>
    <line x1="320" y1="80" x2="350" y2="130" stroke="{INK}" stroke-width="4"/>
    <rect x="330" y="120" width="60" height="20" rx="6" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <!-- witness box -->
    <rect x="440" y="300" width="160" height="160" rx="4" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="440" y1="340" x2="600" y2="340" stroke="{INK}" stroke-width="2.5" opacity="0.5"/>
    <!-- railing -->
    <line x1="60" y1="340" x2="420" y2="340" stroke="{INK}" stroke-width="4"/>
    <line x1="80" y1="280" x2="80" y2="440" stroke="{INK}" stroke-width="3"/>
    <line x1="160" y1="280" x2="160" y2="440" stroke="{INK}" stroke-width="3"/>
    <line x1="240" y1="280" x2="240" y2="440" stroke="{INK}" stroke-width="3"/>
    <line x1="320" y1="280" x2="320" y2="440" stroke="{INK}" stroke-width="3"/>
    """

# ── Foreground props ──────────────────────────────────────────────────

def _prop_briefcase(x=200, y=300) -> str:
    return f"""
    <rect x="{x}" y="{y+20}" width="200" height="140" rx="10" fill="none" stroke="{INK}" stroke-width="4.5"/>
    <path d="{x+70},{y} L {x+70},{y+20} M {x+130},{y} L {x+130},{y+20}" stroke="{INK}" stroke-width="0"/>
    <rect x="{x+70}" y="{y}" width="60" height="26" rx="6" fill="none" stroke="{INK}" stroke-width="3.5"/>
    <line x1="{x}" y1="{y+90}" x2="{x+200}" y2="{y+90}" stroke="{INK}" stroke-width="3" opacity="0.5"/>
    <rect x="{x+82}" y="{y+80}" width="36" height="20" rx="4" fill="none" stroke="{INK}" stroke-width="3"/>
    """

def _prop_phone(x=200, y=200) -> str:
    return f"""
    <rect x="{x}" y="{y}" width="110" height="190" rx="16" fill="none" stroke="{INK}" stroke-width="4.5"/>
    <rect x="{x+10}" y="{y+16}" width="90" height="148" rx="6" fill="none" stroke="{INK}" stroke-width="2.5" opacity="0.4"/>
    <circle cx="{x+55}" cy="{y+175}" r="10" fill="none" stroke="{INK}" stroke-width="3"/>
    <line x1="{x+40}" y1="{y+10}" x2="{x+70}" y2="{y+10}" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>
    """

def _prop_coins(x=160, y=300) -> str:
    return f"""
    <ellipse cx="{x+100}" cy="{y+80}" rx="90" ry="24" fill="none" stroke="{GOLD}" stroke-width="3.5"/>
    <line x1="{x+10}" y1="{y+80}" x2="{x+10}" y2="{y+48}" stroke="{GOLD}" stroke-width="3.5"/>
    <line x1="{x+190}" y1="{y+80}" x2="{x+190}" y2="{y+48}" stroke="{GOLD}" stroke-width="3.5"/>
    <ellipse cx="{x+100}" cy="{y+48}" rx="90" ry="24" fill="none" stroke="{GOLD}" stroke-width="3.5"/>
    <line x1="{x+10}" y1="{y+48}" x2="{x+10}" y2="{y+18}" stroke="{GOLD}" stroke-width="3.5"/>
    <line x1="{x+190}" y1="{y+48}" x2="{x+190}" y2="{y+18}" stroke="{GOLD}" stroke-width="3.5"/>
    <ellipse cx="{x+100}" cy="{y+18}" rx="90" ry="24" fill="none" stroke="{GOLD}" stroke-width="3.5"/>
    <text x="{x+78}" y="{y+28}" font-size="28" font-weight="900" fill="none" stroke="{GOLD}" stroke-width="1.8">₹</text>
    """

def _prop_rejection_letters(x=120, y=280, count=5) -> str:
    parts = []
    for i in range(min(count, 7)):
        ox = x + i * 22
        oy = y - i * 12
        parts.append(f"""
        <rect x="{ox}" y="{oy}" width="160" height="120" rx="4"
              fill="none" stroke="{INK}" stroke-width="3" opacity="{0.4+i*0.1:.1f}"/>
        <line x1="{ox+20}" y1="{oy+30}" x2="{ox+140}" y2="{oy+30}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
        <line x1="{ox+20}" y1="{oy+50}" x2="{ox+120}" y2="{oy+50}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
        <line x1="{ox+20}" y1="{oy+70}" x2="{ox+130}" y2="{oy+70}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
        """)
    # Red X on top letter
    top_x = x + (count-1)*22
    top_y = y - (count-1)*12
    parts.append(f"""
    <line x1="{top_x+30}" y1="{top_y+25}" x2="{top_x+130}" y2="{top_y+95}" stroke="{RED}" stroke-width="5"/>
    <line x1="{top_x+130}" y1="{top_y+25}" x2="{top_x+30}" y2="{top_y+95}" stroke="{RED}" stroke-width="5"/>
    """)
    return "".join(parts)

def _prop_trophy(x=220, y=200) -> str:
    return f"""
    <path d="M {x+30} {y} L {x+170} {y} L {x+155} {y+100}
             Q {x+140} {y+140} {x+100} {y+150}
             Q {x+60} {y+140} {x+45} {y+100} Z"
          fill="none" stroke="{GOLD}" stroke-width="4.5"/>
    <path d="M {x+30} {y+15} Q {x} {y+15} {x} {y+55} Q {x} {y+90} {x+45} {y+100}"
          fill="none" stroke="{GOLD}" stroke-width="3.5"/>
    <path d="M {x+170} {y+15} Q {x+200} {y+15} {x+200} {y+55} Q {x+200} {y+90} {x+155} {y+100}"
          fill="none" stroke="{GOLD}" stroke-width="3.5"/>
    <line x1="{x+75}" y1="{y+150}" x2="{x+75}" y2="{y+185}" stroke="{GOLD}" stroke-width="4"/>
    <rect x="{x+50}" y="{y+185}" width="100" height="22" rx="6" fill="none" stroke="{GOLD}" stroke-width="4"/>
    <polygon points="{x+100},{y-20} {x+108},{y-5} {x+125},{y-5} {x+112},{y+5} {x+117},{y+22} {x+100},{y+12} {x+83},{y+22} {x+88},{y+5} {x+75},{y-5} {x+92},{y-5}"
             fill="none" stroke="{GOLD}" stroke-width="2.5"/>
    """

def _prop_graph_up(x=80, y=200) -> str:
    bars = [(x+40,200),(x+120,150),(x+200,180),(x+280,110),(x+360,70),(x+440,30)]
    bar_w = 60
    parts = [
        f'<line x1="{x+20}" y1="{y+220}" x2="{x+500}" y2="{y+220}" stroke="{INK}" stroke-width="4"/>',
        f'<line x1="{x+20}" y1="{y}" x2="{x+20}" y2="{y+225}" stroke="{INK}" stroke-width="4"/>',
    ]
    for i,(bx,bh) in enumerate(bars):
        col = GOLD if i == len(bars)-1 else INK
        alpha = "1" if i == len(bars)-1 else "0.7"
        parts.append(f'<rect x="{bx}" y="{y+bh}" width="{bar_w}" height="{220-bh}" rx="4" fill="none" stroke="{col}" stroke-width="{4 if i==len(bars)-1 else 3}" opacity="{alpha}"/>')
    # Arrow up on last bar
    parts.append(f'<line x1="{x+470}" y1="{y+50}" x2="{x+470}" y2="{y}" stroke="{RED}" stroke-width="4"/>')
    parts.append(f'<polygon points="{x+458},{y+15} {x+470},{y} {x+482},{y+15}" fill="{RED}"/>')
    return "".join(parts)

def _prop_clock(x=220, y=180) -> str:
    return f"""
    <circle cx="{x+100}" cy="{y+100}" r="100" fill="none" stroke="{INK}" stroke-width="4.5"/>
    <circle cx="{x+100}" cy="{y+100}" r="8" fill="{INK}"/>
    <!-- hour ticks -->
    <line x1="{x+100}" y1="{y+8}" x2="{x+100}" y2="{y+22}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+100}" y1="{y+178}" x2="{x+100}" y2="{y+192}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+8}" y1="{y+100}" x2="{x+22}" y2="{y+100}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+178}" y1="{y+100}" x2="{x+192}" y2="{y+100}" stroke="{INK}" stroke-width="4"/>
    <!-- hands -->
    <line x1="{x+100}" y1="{y+100}" x2="{x+100}" y2="{y+40}" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>
    <line x1="{x+100}" y1="{y+100}" x2="{x+150}" y2="{y+110}" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>
    """

def _prop_newspaper(x=100, y=260) -> str:
    return f"""
    <rect x="{x}" y="{y}" width="400" height="280" rx="4" fill="none" stroke="{INK}" stroke-width="4"/>
    <!-- masthead -->
    <rect x="{x}" y="{y}" width="400" height="55" rx="4" fill="none" stroke="{INK}" stroke-width="3"/>
    <line x1="{x+20}" y1="{y+28}" x2="{x+380}" y2="{y+28}" stroke="{INK}" stroke-width="2.5" opacity="0.6"/>
    <!-- headline -->
    <line x1="{x+20}" y1="{y+75}" x2="{x+380}" y2="{y+75}" stroke="{INK}" stroke-width="5"/>
    <line x1="{x+20}" y1="{y+95}" x2="{x+300}" y2="{y+95}" stroke="{INK}" stroke-width="5"/>
    <!-- columns -->
    <line x1="{x+200}" y1="{y+115}" x2="{x+200}" y2="{y+270}" stroke="{INK}" stroke-width="2" opacity="0.3"/>
    <line x1="{x+20}" y1="{y+120}" x2="{x+185}" y2="{y+120}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
    <line x1="{x+20}" y1="{y+135}" x2="{x+185}" y2="{y+135}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
    <line x1="{x+20}" y1="{y+150}" x2="{x+175}" y2="{y+150}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
    <line x1="{x+215}" y1="{y+120}" x2="{x+380}" y2="{y+120}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
    <line x1="{x+215}" y1="{y+135}" x2="{x+370}" y2="{y+135}" stroke="{INK}" stroke-width="2" opacity="0.4"/>
    """

def _prop_lightbulb_large(x=220, y=140) -> str:
    return f"""
    <path d="M {x+100} {y} A 80 80 0 0 1 {x+180} {y+80}
             C {x+180} {y+120} {x+160} {y+140} {x+155} {y+155}
             L {x+45} {y+155}
             C {x+40} {y+140} {x+20} {y+120} {x+20} {y+80}
             A 80 80 0 0 1 {x+100} {y} Z"
          fill="none" stroke="{GOLD}" stroke-width="4.5"/>
    <line x1="{x+68}" y1="{y+155}" x2="{x+68}" y2="{y+185}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+100}" y1="{y+155}" x2="{x+100}" y2="{y+190}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+132}" y1="{y+155}" x2="{x+132}" y2="{y+185}" stroke="{INK}" stroke-width="4"/>
    <line x1="{x+60}" y1="{y+185}" x2="{x+140}" y2="{y+185}" stroke="{INK}" stroke-width="3"/>
    <line x1="{x+68}" y1="{y+195}" x2="{x+132}" y2="{y+195}" stroke="{INK}" stroke-width="3"/>
    <!-- glow rays -->
    <line x1="{x+100}" y1="{y-20}" x2="{x+100}" y2="{y-42}" stroke="{GOLD}" stroke-width="3" opacity="0.6"/>
    <line x1="{x+165}" y1="{y+15}" x2="{x+185}" y2="{y}" stroke="{GOLD}" stroke-width="3" opacity="0.6"/>
    <line x1="{x+35}" y1="{y+15}" x2="{x+15}" y2="{y}" stroke="{GOLD}" stroke-width="3" opacity="0.6"/>
    """

# ── Keyword → (environment, prop) mapping ────────────────────────────

_SCENE_MAP = {
    # Work / business
    "office":         (_env_office,     _prop_briefcase),
    "அலுவலக":        (_env_office,     _prop_briefcase),
    "வேலை":          (_env_office,     _prop_briefcase),
    "job":            (_env_office,     _prop_briefcase),
    "company":        (_env_office,     _prop_briefcase),
    "நிறுவனம்":      (_env_office,     _prop_graph_up),
    "meeting":        (_env_office,     _prop_newspaper),
    "ceo":            (_env_office,     _prop_briefcase),
    "founder":        (_env_office,     _prop_lightbulb_large),
    "startup":        (_env_office,     _prop_lightbulb_large),

    # Street / city
    "street":         (_env_street,     _prop_newspaper),
    "city":           (_env_street,     _prop_phone),
    "வீதி":           (_env_street,     _prop_newspaper),

    # Money
    "money":          (_env_office,     _prop_coins),
    "சம்பளம்":       (_env_office,     _prop_coins),
    "₹":              (_env_office,     _prop_coins),
    "salary":         (_env_office,     _prop_coins),
    "debt":           (_env_home,       _prop_coins),
    "கடன்":           (_env_home,       _prop_coins),

    # Rejection / failure
    "rejected":       (_env_office,     _prop_rejection_letters),
    "rejection":      (_env_office,     _prop_rejection_letters),
    "நிராகரி":       (_env_office,     _prop_rejection_letters),
    "failure":        (_env_street,     _prop_rejection_letters),
    "தோல்வி":        (_env_street,     _prop_rejection_letters),

    # Success / win
    "trophy":         (_env_mountain,   _prop_trophy),
    "வெற்றி":        (_env_mountain,   _prop_trophy),
    "success":        (_env_mountain,   _prop_trophy),
    "won":            (_env_mountain,   _prop_trophy),

    # Growth
    "growth":         (_env_office,     _prop_graph_up),
    "வளர்ச்சி":      (_env_office,     _prop_graph_up),
    "profit":         (_env_office,     _prop_graph_up),

    # Home / family
    "home":           (_env_home,       _prop_phone),
    "வீடு":           (_env_home,       _prop_phone),
    "family":         (_env_home,       _prop_newspaper),
    "குடும்பம்":     (_env_home,       _prop_newspaper),

    # Prison / struggle
    "prison":         (_env_jail,       _prop_rejection_letters),
    "jail":           (_env_jail,       _prop_rejection_letters),
    "சிறை":          (_env_jail,       _prop_rejection_letters),

    # Ideas / insight
    "idea":           (_env_library,    _prop_lightbulb_large),
    "யோசனை":        (_env_library,    _prop_lightbulb_large),
    "insight":        (_env_library,    _prop_lightbulb_large),
    "invention":      (_env_library,    _prop_lightbulb_large),

    # Food / restaurant
    "restaurant":     (_env_restaurant, _prop_coins),
    "food":           (_env_restaurant, _prop_coins),
    "உணவு":          (_env_restaurant, _prop_coins),
    "kfc":            (_env_restaurant, _prop_rejection_letters),

    # Mountain / journey
    "mountain":       (_env_mountain,   _prop_trophy),
    "மலை":           (_env_mountain,   _prop_trophy),
    "journey":        (_env_mountain,   _prop_briefcase),
    "struggle":       (_env_mountain,   _prop_rejection_letters),

    # Time
    "years":          (_env_office,     _prop_clock),
    "ஆண்டு":        (_env_office,     _prop_clock),
    "time":           (_env_office,     _prop_clock),
    "நேரம்":        (_env_office,     _prop_clock),
}

_DEFAULT_ENV   = _env_office
_DEFAULT_PROPS = [_prop_briefcase, _prop_lightbulb_large, _prop_coins,
                  _prop_trophy, _prop_graph_up]


def _pick_scene(text: str, visual_keywords: list, scene_index: int):
    """Return (env_fn, prop_fn) based on keywords."""
    combined = (text + " " + " ".join(visual_keywords)).lower()
    for kw, (env_fn, prop_fn) in _SCENE_MAP.items():
        if kw in combined:
            return env_fn, prop_fn
    return _DEFAULT_ENV, _DEFAULT_PROPS[scene_index % len(_DEFAULT_PROPS)]


def _build_panel_svg(env_fn, prop_fn, progress: float, scene_index: int) -> str:
    """Build layered SVG panel with progress-based reveal."""
    # Clip width for draw-on reveal
    clip_w = int(PW * min(1.0, progress * 1.6))
    env_content = env_fn()
    prop_content = prop_fn()

    return f"""<svg width="{PW}" height="{PH}" viewBox="0 0 {PW} {PH}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="reveal">
      <rect x="0" y="0" width="{clip_w}" height="{PH}"/>
    </clipPath>
  </defs>
  <!-- white paper bg -->
  <rect width="{PW}" height="{PH}" fill="#FAFAF7"/>
  <!-- horizontal rule lines (notebook feel) -->
  {"".join(f'<line x1="0" y1="{y}" x2="{PW}" y2="{y}" stroke="#E8E4DC" stroke-width="1"/>' for y in range(0, PH, 52))}
  <!-- environment -->
  <g clip-path="url(#reveal)" opacity="{min(1.0, progress*2):.2f}">
    {env_content}
  </g>
  <!-- prop overlay (draws in after env) -->
  <g clip-path="url(#reveal)" opacity="{min(1.0, max(0.0, (progress-0.3)*2.5)):.2f}">
    {prop_content}
  </g>
  <!-- subtle border -->
  <rect width="{PW}" height="{PH}" fill="none" stroke="#D8D4CC" stroke-width="3" rx="8"/>
</svg>"""


def render_scene_panel(
    narration_text: str,
    visual_keywords: list,
    scene_index: int,
    progress: float,
    size: tuple = (PW, PH),
) -> Image.Image:
    """Render the illustrated scene panel as a PIL RGBA image."""
    env_fn, prop_fn = _pick_scene(narration_text, visual_keywords, scene_index)
    svg = _build_panel_svg(env_fn, prop_fn, progress, scene_index)
    try:
        png_bytes = cairosvg.svg2png(
            bytestring=svg.encode(),
            output_width=size[0],
            output_height=size[1],
        )
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        # Fallback: blank cream panel
        img = Image.new("RGBA", size, (250, 248, 242, 255))
        return img
