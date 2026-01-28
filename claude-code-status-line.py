#!/usr/bin/env python3
"""
Simple Claude Code StatusLine Script
Shows context usage/progress with colored bar
Uses current_usage field for accurate context window calculations

INSTALLATION:
1. Save this file to ~/.claude/claude-code-status-line.py
2. Make it executable:
   chmod +x ~/.claude/claude-code-status-line.py
3. Add to ~/.claude/settings.json:
   {
     "statusLine": {
       "type": "command",
       "command": "~/.claude/claude-code-status-line.py"
     }
   }
4. Set THEME below to 'dark' or 'light'
5. Restart Claude Code

Note: After initial setup, edits to this script take effect immediately (no restart needed).

Latest version: https://github.com/benabraham/claude-code-status-line
"""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

# =============================================================================
# CONFIGURATION — override any setting via environment variables (SL_ prefix)
# Example: SL_THEME=light SL_SEGMENTS='model percentage directory' ~/.claude/claude-code-status-line.py
# =============================================================================


def _env_str(key, default):
    return os.environ.get(f"SL_{key}", default)


def _env_int(key, default):
    try:
        return int(os.environ.get(f"SL_{key}", default))
    except (ValueError, TypeError):
        return default


THEME = _env_str("THEME", "dark")
USAGE_CACHE_DURATION = _env_int("USAGE_CACHE_DURATION", 300)
THEME_FILE = _env_str("THEME_FILE", os.path.expanduser("~/.claude/claude-code-theme.toml"))

# --- Segment system ---

DEFAULT_SEGMENTS = 'model progress_bar percentage tokens directory git_branch usage_5hour usage_weekly'
VALID_SEGMENTS = frozenset(DEFAULT_SEGMENTS.split())

SEGMENT_DEFAULTS = {
    'progress_bar': {'width': '12'},
    'git_branch': {'hide_default': '1'},
    'percentage': {'fallback': '1'},
    'tokens': {'fallback': '1'},
    'usage_5hour': {'gauge': 'blocks', 'width': '4'},
    'usage_weekly': {'gauge': 'blocks', 'width': '4'},
}


def _parse_segments(raw):
    """Parse 'segment:key=val:key=val ...' into [(name, {opts}), ...]"""
    if raw is None:
        raw = DEFAULT_SEGMENTS
    stripped = raw.strip()
    if not stripped:
        return []
    result = []
    for token in stripped.split():
        parts = token.split(':')
        name = parts[0]
        if name not in VALID_SEGMENTS:
            continue
        opts = dict(SEGMENT_DEFAULTS.get(name, {}))
        for part in parts[1:]:
            if '=' in part:
                k, v = part.split('=', 1)
                opts[k] = v
        if 'width' in opts:
            try:
                w = int(opts['width'])
                if name in ('usage_5hour', 'usage_weekly'):
                    if w < 2 or w % 2 != 0 or w > 128:
                        opts['width'] = '4'
                elif name == 'progress_bar':
                    if w < 1 or w > 128:
                        opts['width'] = '12'
            except ValueError:
                opts['width'] = '4' if name in ('usage_5hour', 'usage_weekly') else '12'
        result.append((name, opts))
    return result


SEGMENTS = _parse_segments(os.environ.get('SL_SEGMENTS'))


def _has_segment(name):
    return any(n == name for n, _ in SEGMENTS)


def _segment_opts(name):
    for n, opts in SEGMENTS:
        if n == name:
            return opts
    return SEGMENT_DEFAULTS.get(name, {})

# =============================================================================
# HEX COLOR CONVERSION (needed before theme loading)
# =============================================================================


def hex_to_rgb(hex_color):
    """Convert '#RRGGBB' hex string to (R, G, B) tuple"""
    if hex_color is None:
        return None
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return None
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


# 6x6x6 color cube channel values (indices 0-5)
_CUBE_VALS = (0, 95, 135, 175, 215, 255)


def hex_to_256(hex_color):
    """Convert '#RRGGBB' hex to nearest xterm-256 color index."""
    rgb = hex_to_rgb(hex_color)
    if rgb is None:
        return 0
    r, g, b = rgb

    # Nearest in 6x6x6 cube (indices 16-231)
    ri = min(range(6), key=lambda i: abs(r - _CUBE_VALS[i]))
    gi = min(range(6), key=lambda i: abs(g - _CUBE_VALS[i]))
    bi = min(range(6), key=lambda i: abs(b - _CUBE_VALS[i]))
    cube_idx = 16 + 36 * ri + 6 * gi + bi
    cr, cg, cb = _CUBE_VALS[ri], _CUBE_VALS[gi], _CUBE_VALS[bi]
    cube_dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2

    # Nearest in grayscale ramp (indices 232-255, values 8,18,...,238)
    gray_i = min(max(0, round((r * 0.299 + g * 0.587 + b * 0.114 - 8) / 10)), 23)
    gray_v = 8 + 10 * gray_i
    gray_dist = (r - gray_v) ** 2 + (g - gray_v) ** 2 + (b - gray_v) ** 2

    return 232 + gray_i if gray_dist < cube_dist else cube_idx


# Color format: ("#RRGGBB", fallback_256)
# Set hex to None to always use 256 fallback

THEMES = {
    "dark": {
        # Model badge colors: (bg, fg)
        "model_sonnet": (("#A3BE8C", 108), ("#2E3440", 236)),  # nord14 bg, nord0 fg
        "model_opus": (("#88C0D0", 110), ("#2E3440", 236)),  # nord8 bg, nord0 fg
        "model_haiku": (("#4C566A", 60), ("#ECEFF4", 255)),  # nord3 bg, nord6 fg
        "model_default": (("#D8DEE9", 253), ("#2E3440", 236)),  # nord4 bg, nord0 fg
        # Unused portion of progress bar
        "bar_empty": ("#292c33", 234),  # darker than nord0
        # Text colors (Nord)
        "text_percent": (("#5E81AC", None), 67),  # nord10
        "text_numbers": (("#5E81AC", None), 67),  # nord10
        "text_cwd": (("#81A1C1", None), 110),  # nord9
        "text_git": (("#B48EAD", None), 139),  # nord15 purple
        "text_na": (("#D08770", None), 173),  # nord12 orange
        # Usage indicator colors (ratio-based)
        "usage_light": ("#88C0D0", 110),  # nord8 frost - well ahead
        "usage_green": ("#A3BE8C", 108),  # nord14 - on track
        "usage_yellow": ("#EBCB8B", 222),  # nord13 - using faster
        "usage_red": ("#BF616A", 131),  # nord11 - burning through
        # Progress bar gradient: (threshold, (hex, fallback_256))
        # Threshold means "use this color if pct < threshold"
        "gradient": [
            (10, ("#183522", 22)),  # 0-9%   dark green
            (20, ("#153E21", 22)),  # 10-19%
            (30, ("#104620", 28)),  # 20-29%
            (40, ("#0B4E1C", 28)),  # 30-39%
            (50, ("#065716", 34)),  # 40-49% bright green
            (60, ("#2E5900", 106)),  # 50-59% yellow-green
            (70, ("#5D4F00", 136)),  # 60-69% olive
            (80, ("#833A00", 166)),  # 70-79% orange
            (90, ("#A10700", 160)),  # 80-89% red-orange
            (101, ("#B30000", 196)),  # 90-100% red
        ],
    },
    "light": {
        # Model badge colors: (bg, fg)
        "model_sonnet": (
            ("#8FAA78", 107),
            ("#FFFFFF", 231),
        ),  # muted green bg, white fg
        "model_opus": (("#6AA2B2", 73), ("#FFFFFF", 231)),  # muted aqua bg, white fg
        "model_haiku": (("#8C96AA", 103), ("#FFFFFF", 231)),  # muted grey bg, white fg
        "model_default": (("#646E82", 66), ("#FFFFFF", 231)),  # slate bg, white fg
        # Unused portion of progress bar
        "bar_empty": ("#D8DEE9", 253),  # nord4
        # Text colors
        "text_percent": (("#505050", None), 240),  # dark grey
        "text_numbers": (("#505050", None), 240),  # dark grey
        "text_cwd": (("#3C465A", None), 238),  # dark slate
        "text_git": (("#508C50", None), 65),  # muted green
        "text_na": (("#D08770", None), 173),  # nord12 orange
        # Usage indicator colors (ratio-based) - darker for light bg
        "usage_light": ("#2B7A78", 30),  # dark teal - well ahead
        "usage_green": ("#4A7C4A", 65),  # dark green - on track
        "usage_yellow": ("#9A7B00", 136),  # dark yellow/gold - using faster
        "usage_red": ("#A03030", 124),  # dark red - burning through
        # Progress bar gradient
        "gradient": [
            (10, ("#22783C", 29)),  # 0-9%   green
            (20, ("#228237", 29)),  # 10-19%
            (30, ("#228C32", 35)),  # 20-29%
            (40, ("#329628", 35)),  # 30-39%
            (50, ("#46A01E", 70)),  # 40-49%
            (60, ("#828C00", 142)),  # 50-59% yellow-green
            (70, ("#A08200", 178)),  # 60-69% olive/yellow
            (80, ("#B46400", 172)),  # 70-79% orange
            (90, ("#C83C00", 166)),  # 80-89% red-orange
            (101, ("#D21E1E", 160)),  # 90-100% red
        ],
    },
}


def _load_custom_theme():
    """Load custom theme from TOML file and merge into THEMES.

    Only defined keys override the base theme; everything else inherits.

    Expected TOML format:
        # Model badges: [bg_hex, fg_hex]
        model_sonnet = ["#A3BE8C", "#2E3440"]
        model_opus = ["#88C0D0", "#2E3440"]
        model_haiku = ["#4C566A", "#ECEFF4"]
        model_default = ["#D8DEE9", "#2E3440"]

        # Simple colors
        bar_empty = "#292c33"
        usage_light = "#88C0D0"
        usage_green = "#A3BE8C"
        usage_yellow = "#EBCB8B"
        usage_red = "#BF616A"

        # Text colors
        text_percent = "#5E81AC"
        text_numbers = "#5E81AC"
        text_cwd = "#81A1C1"
        text_git = "#B48EAD"
        text_na = "#D08770"

        # Gradient: array of {threshold, color} tables
        gradient = [
            {threshold = 10, color = "#183522"},
            {threshold = 20, color = "#153E21"},
        ]
    """
    if not os.path.isfile(THEME_FILE):
        return

    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            return

    try:
        with open(THEME_FILE, 'rb') as f:
            ns = tomllib.load(f)
    except Exception:
        return

    # Build override dict, converting TOML values to internal tuple format
    overrides = {}

    def _is_hex(v):
        return isinstance(v, str) and v.startswith('#') and len(v) == 7

    # Model badges: ["bg_hex", "fg_hex"] → (("bg_hex", 256), ("fg_hex", 256))
    for key in ("model_sonnet", "model_opus", "model_haiku", "model_default"):
        if key in ns:
            val = ns[key]
            if not isinstance(val, list) or len(val) != 2:
                continue
            bg_hex, fg_hex = val
            if not _is_hex(bg_hex) or not _is_hex(fg_hex):
                continue
            overrides[key] = ((bg_hex, hex_to_256(bg_hex)), (fg_hex, hex_to_256(fg_hex)))

    # Simple colors: "hex" → ("hex", 256)
    for key in ("bar_empty", "usage_light", "usage_green", "usage_yellow", "usage_red"):
        if key in ns:
            h = ns[key]
            if not _is_hex(h):
                continue
            overrides[key] = (h, hex_to_256(h))

    # Text colors: "hex" → (("hex", None), 256)
    for key in ("text_percent", "text_numbers", "text_cwd", "text_git", "text_na"):
        if key in ns:
            h = ns[key]
            if not _is_hex(h):
                continue
            overrides[key] = ((h, None), hex_to_256(h))

    # Gradient: [{threshold, color}, ...] → [(threshold, ("hex", 256)), ...]
    if "gradient" in ns:
        raw = ns["gradient"]
        if isinstance(raw, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("threshold"), (int, float))
            and _is_hex(item.get("color", ""))
            for item in raw
        ):
            overrides["gradient"] = [
                (item["threshold"], (item["color"], hex_to_256(item["color"])))
                for item in raw
            ]

    if not overrides:
        return

    # Merge into base theme (selected by THEME), register as "custom"
    global THEME
    base = THEMES.get(THEME, THEMES["dark"])
    THEMES["custom"] = {**base, **overrides}
    THEME = "custom"


_load_custom_theme()

# =============================================================================
# COLOR SUPPORT DETECTION
# =============================================================================


def supports_truecolor():
    """Detect if terminal supports 24-bit true color"""
    colorterm = os.environ.get("COLORTERM", "").lower()
    return colorterm in ("truecolor", "24bit")


TRUECOLOR = supports_truecolor()

# =============================================================================
# ANSI ESCAPE HELPERS
# =============================================================================

RESET = "\033[0m"
BOLD = "\033[1m"


def _color(rgb, fallback_256, is_bg=False):
    """Generate ANSI color code with truecolor/256 fallback. RGB can be hex string or tuple."""
    prefix = 48 if is_bg else 38
    if TRUECOLOR and rgb is not None:
        if isinstance(rgb, str):
            rgb = hex_to_rgb(rgb)
        return f"\033[{prefix};2;{rgb[0]};{rgb[1]};{rgb[2]}m"
    else:
        return f"\033[{prefix};5;{fallback_256}m"


def fg_themed(color_tuple):
    """Foreground color from theme tuple ((rgb, _), fallback) or ((rgb, fallback), _)"""
    if isinstance(color_tuple[0], tuple):
        rgb, fallback = color_tuple[0]
        if fallback is None:
            fallback = color_tuple[1]
    else:
        rgb, fallback = color_tuple
    return _color(rgb, fallback, is_bg=False)


def bg_themed(color_tuple):
    """Background color from theme tuple ((rgb, fallback), _)"""
    rgb, fallback = color_tuple[0]
    return _color(rgb, fallback, is_bg=True)


def fg_gradient(rgb, fallback_256):
    """Foreground from gradient tuple"""
    return _color(rgb, fallback_256, is_bg=False)


def fg_empty():
    """Foreground for empty bar portion"""
    theme = THEMES[THEME]
    rgb, fallback = theme["bar_empty"]
    return _color(rgb, fallback, is_bg=False)


# =============================================================================
# THEME-AWARE COLOR FUNCTIONS
# =============================================================================


def get_colors_for_percentage(pct):
    """Return (rgb, fallback_256) for progress bar fill at given percentage"""
    theme = THEMES[THEME]
    for threshold, color in theme["gradient"]:
        if pct < threshold:
            return color
    return theme["gradient"][-1][1]


def get_model_colors(model):
    """Return (bg_code, fg_code) for model badge"""
    theme = THEMES[THEME]
    if "Sonnet" in model:
        key = "model_sonnet"
    elif "Opus" in model:
        key = "model_opus"
    elif "Haiku" in model:
        key = "model_haiku"
    else:
        key = "model_default"

    bg_tuple, fg_tuple = theme[key]
    bg_code = _color(bg_tuple[0], bg_tuple[1], is_bg=True)
    fg_code = _color(fg_tuple[0], fg_tuple[1], is_bg=False)
    return bg_code + BOLD + fg_code


def text_color(key):
    """Get text color by key: 'percent', 'numbers', 'cwd', 'git'"""
    theme = THEMES[THEME]
    color_tuple = theme[f"text_{key}"]
    return fg_themed(color_tuple)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def center_text(text, min_width=12):
    """Center text with 1-char padding on each side, minimum 12 chars wide"""
    width = max(min_width, len(text) + 2)
    padding = (width - len(text)) // 2
    right_padding = width - len(text) - padding
    return " " * padding + text + " " * right_padding


def get_git_branch(cwd):
    """Get current git branch, or None"""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "-c", "color.branch=never", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=0.3,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            branch = re.sub(r'\x1b\[[0-9;]*m', '', branch)
            if branch:
                return branch
            return None
    except Exception:
        pass
    return None



# =============================================================================
# TRANSCRIPT PARSING (for comparison with API - remove when bug #13783 is fixed)
# =============================================================================


def get_tokens_from_transcript(transcript_path):
    """Parse JSONL transcript for accurate context tokens."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    latest_usage = None
    latest_timestamp = None
    total_output_tokens = 0

    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("isSidechain") or entry.get("isApiErrorMessage"):
                        continue
                    usage = entry.get("message", {}).get("usage")
                    timestamp = entry.get("timestamp")
                    if usage and timestamp:
                        total_output_tokens += usage.get("output_tokens", 0)
                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_usage = usage
                except json.JSONDecodeError:
                    continue
    except (IOError, OSError):
        return None

    if latest_usage:
        return (
            latest_usage.get("input_tokens", 0)
            + latest_usage.get("cache_read_input_tokens", 0)
            + latest_usage.get("cache_creation_input_tokens", 0)
            + total_output_tokens
        )
    return None


# =============================================================================
# USAGE LIMITS API
# =============================================================================

USAGE_CACHE_PATH = os.path.expanduser("~/.claude/.usage_cache.json")
CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")


def get_oauth_token():
    """Get OAuth access token from macOS Keychain or credentials file."""
    # On macOS, try Keychain first
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    "Claude Code-credentials",
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                creds = json.loads(result.stdout.strip())
                return creds.get("claudeAiOauth", {}).get("accessToken")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    # Fallback to credentials file (Linux, Windows, or if Keychain fails)
    try:
        with open(CREDENTIALS_PATH, "r") as f:
            creds = json.load(f)
        return creds.get("claudeAiOauth", {}).get("accessToken")
    except (IOError, json.JSONDecodeError, KeyError):
        return None


def fetch_usage_data():
    """Fetch usage data from Anthropic OAuth API, with caching."""
    # Check cache first
    try:
        if os.path.exists(USAGE_CACHE_PATH):
            with open(USAGE_CACHE_PATH, "r") as f:
                cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < USAGE_CACHE_DURATION:
                return cache.get("data")
    except (IOError, json.JSONDecodeError):
        pass

    # Get OAuth token and validate it contains only safe characters
    token = get_oauth_token()
    if not token:
        return None
    if not all(c.isalnum() or c in '-._~+/=' for c in token):
        return None

    # Fetch from API using curl (token passed via --config stdin to hide from ps)
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-f",
                "--config", "-",
                "-H", "Accept: application/json",
                "-H", "Content-Type: application/json",
                "-H", "User-Agent: claude-code/2.0.32",
                "-H", "anthropic-beta: oauth-2025-04-20",
                "https://api.anthropic.com/api/oauth/usage",
            ],
            input=f'header = "Authorization: Bearer {token}"\n',
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)

        # Cache the result atomically to avoid corruption from concurrent reads
        tmp_path = None
        try:
            cache_dir = os.path.dirname(USAGE_CACHE_PATH)
            fd, tmp_path = tempfile.mkstemp(dir=cache_dir)
            with os.fdopen(fd, 'w') as f:
                json.dump({"timestamp": time.time(), "data": data}, f)
            os.replace(tmp_path, USAGE_CACHE_PATH)
        except (IOError, OSError):
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def get_usage_color(ratio):
    """Get foreground color for usage indicator based on time/usage ratio."""
    theme = THEMES[THEME]
    if ratio >= 1 / 0.75:
        rgb, fallback = theme["usage_light"]
    elif ratio >= 1.0:
        rgb, fallback = theme["usage_green"]
    elif ratio >= 0.75:
        rgb, fallback = theme["usage_yellow"]
    else:
        rgb, fallback = theme["usage_red"]

    return _color(rgb, fallback, is_bg=False)


def get_usage_gauge(ratio):
    """Get gauge character showing usage vs time ratio.

    - ratio > 1 (ahead): fills from TOP with green, using BG/FG trick
    - ratio < 1 (behind): fills from BOTTOM with yellow/red, FG only
    """
    theme = THEMES[THEME]
    gauges = "▁▂▃▄▅▆▇█"  # fills from bottom

    if ratio >= 1.0:
        # Ahead - show how much ahead, filling from top (green)
        # Use BG = green, FG = empty to create top-fill illusion
        ahead = min(1.0, ratio - 1.0)  # 0 = exactly on track, 1 = way ahead

        empty_rgb, empty_fb = theme["bar_empty"]
        ahead_key = "usage_light" if ratio >= 1 / 0.75 else "usage_green"
        green_rgb, green_fb = theme[ahead_key]

        # Invert gauge for top-fill: more ahead = more visible from top
        index = int(ahead * 7.99)
        index = max(0, min(7, index))
        # Use █ (full FG) when minimal - shows dark (empty), not green
        char = gauges[7 - index] if index > 0 else "█"

        bg = _color(green_rgb, green_fb, is_bg=True)
        fg = _color(empty_rgb, empty_fb, is_bg=False)
        return f"{bg}{fg}{char}{RESET}"
    else:
        # Behind - show how much behind, filling from bottom (yellow/red)
        behind = min(1.0, 1.0 - ratio)  # 0 = on track, 1 = critical

        empty_rgb, empty_fb = theme["bar_empty"]
        if ratio >= 0.75:
            warn_rgb, warn_fb = theme["usage_yellow"]
        else:
            warn_rgb, warn_fb = theme["usage_red"]

        index = int(behind * 7.99)
        index = max(0, min(7, index))
        # Use space if index is 0 (too small to show)
        char = gauges[index] if index > 0 else " "

        bg = _color(empty_rgb, empty_fb, is_bg=True)
        fg = _color(warn_rgb, warn_fb, is_bg=False)
        return f"{bg}{fg}{char}{RESET}"


def get_usage_gauge_blocks(ratio, gauge_width=4):
    """Horizontal gauge using partial blocks.

    Left half: green (shows how far ahead, fills right-to-left from center).
    Right half: orange/red (shows how far behind, fills left-to-right from center).
    - ratio >= 1.0: green fills left half
    - ratio < 1.0: orange fills right half
    - ratio < 0.75: red instead of orange
    """
    theme = THEMES[THEME]
    BLOCKS = " ▏▎▍▌▋▊▉█"
    half = gauge_width // 2
    empty_rgb, empty_fb = theme["bar_empty"]
    ahead_key = "usage_light" if ratio >= 1 / 0.75 else "usage_green"
    green_rgb, green_fb = theme[ahead_key]
    empty_bg = _color(empty_rgb, empty_fb, is_bg=True)

    parts = []

    if ratio >= 1.0:
        ahead = min(1.0, ratio - 1.0)
        total = round(ahead * half * 8)
        filled = total // 8
        partial = total % 8
        empty = half - filled - (1 if partial > 0 else 0)

        # Left half: [empty...][transition][filled...] (green grows right-to-left)
        if empty > 0:
            parts.append(f"{empty_bg}{' ' * empty}")
        if partial > 0:
            green_bg = _color(green_rgb, green_fb, is_bg=True)
            empty_fg = _color(empty_rgb, empty_fb, is_bg=False)
            parts.append(f"{green_bg}{empty_fg}{BLOCKS[8 - partial]}")
        if filled > 0:
            green_fg = _color(green_rgb, green_fb, is_bg=False)
            parts.append(f"{green_fg}{'█' * filled}")

        # Right half: all empty
        parts.append(f"{empty_bg}{' ' * half}")
    else:
        behind = min(1.0, 1.0 - ratio)

        if ratio >= 0.75:
            warn_rgb, warn_fb = theme["usage_yellow"]
        else:
            warn_rgb, warn_fb = theme["usage_red"]

        total = round(behind * half * 8)
        filled = total // 8
        partial = total % 8
        empty = half - filled - (1 if partial > 0 else 0)

        # Left half: all empty
        parts.append(f"{empty_bg}{' ' * half}")

        # Right half: [filled...][transition][empty...] (warn grows left-to-right)
        if filled > 0:
            warn_fg = _color(warn_rgb, warn_fb, is_bg=False)
            parts.append(f"{warn_fg}{'█' * filled}")
        if partial > 0:
            warn_fg = _color(warn_rgb, warn_fb, is_bg=False)
            parts.append(f"{empty_bg}{warn_fg}{BLOCKS[partial]}")
        if empty > 0:
            parts.append(f"{empty_bg}{' ' * empty}")

    return "".join(parts) + RESET


def format_usage_indicators(usage_data):
    """Format usage indicators, returning dict of {segment_name: rendered_string}."""
    if usage_data is None:
        na_text = f"   {text_color('na')}usage: N/A"
        return {'usage_5hour': na_text, 'usage_weekly': ''}
    if not usage_data:
        return {'usage_5hour': '', 'usage_weekly': ''}

    results = {}

    # Define limit types: (api_key, window_hours, time_format, segment_name)
    # Use NBSP (\u00a0) between day and time for weekly
    limit_configs = [
        ("five_hour", 5, "%H:%M", "usage_5hour"),
        ("seven_day", 7 * 24, "%a\u00a0%H:%M", "usage_weekly"),
    ]

    for api_key, window_hours, time_fmt, segment_name in limit_configs:
        if not _has_segment(segment_name):
            results[segment_name] = ''
            continue

        opts = _segment_opts(segment_name)
        limit = usage_data.get(api_key)
        if not limit:
            results[segment_name] = ''
            continue

        utilization_pct = limit.get("utilization", 0)  # 0-100 percentage
        resets_at = limit.get("resets_at")

        if not resets_at:
            results[segment_name] = ''
            continue

        # Parse reset time
        try:
            reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            results[segment_name] = ''
            continue

        now = datetime.now(timezone.utc)
        remaining_pct = max(0, int(100 - utilization_pct))
        reset_label = reset_dt.astimezone().strftime(time_fmt)

        # Calculate time elapsed in window
        window_seconds = window_hours * 3600
        window_start = reset_dt.timestamp() - window_seconds
        elapsed_seconds = now.timestamp() - window_start
        time_elapsed_pct = max(0, min(100, (elapsed_seconds / window_seconds) * 100))

        # Forward-looking ratio: remaining_budget / remaining_time
        remaining_budget_pct = max(0, 100 - utilization_pct)
        remaining_time_pct = max(0, 100 - time_elapsed_pct)
        if remaining_time_pct > 0.1:
            ratio = remaining_budget_pct / remaining_time_pct
        elif remaining_budget_pct > 0:
            ratio = 2.0  # Window ending with budget left
        else:
            ratio = 1.0  # Window and budget ending together

        color = get_usage_color(ratio)

        # Override text color for 5h window based on absolute remaining budget
        if api_key == "five_hour":
            if remaining_pct <= 5:
                color = get_usage_color(0)
            elif remaining_pct <= 10 and ratio >= 0.75:
                color = get_usage_color(0.8)

        gauge_style = opts.get('gauge', 'blocks')
        gauge_width = int(opts.get('width', '4'))
        if gauge_style == "none":
            gauge = ""
        elif gauge_style == "blocks":
            gauge = get_usage_gauge_blocks(ratio, gauge_width)
        else:
            gauge = get_usage_gauge(ratio)
        gauge_part = f"{gauge}\u00a0" if gauge else ""
        results[segment_name] = (
            f"   {gauge_part}{color}{remaining_pct}\u00a0%\u00a0→\u00a0{reset_label}"
        )

    for seg in ('usage_5hour', 'usage_weekly'):
        if seg not in results:
            results[seg] = ''

    return results


# =============================================================================
# SEGMENT RENDERERS
# =============================================================================


def _render_model(ctx, opts):
    return ctx['model_color'] + center_text(ctx['model']) + RESET


def _render_progress_bar(ctx, opts):
    return ctx['fill_fg'] + '█' * ctx['filled'] + ctx['transition'] + RESET + ctx['empty_fg_str'] + '█' * ctx['empty']


def _render_percentage(ctx, opts):
    comparison = ctx.get('pct_comparison', '')
    if opts.get('fallback') == '1':
        return RESET + text_color('percent') + f' {ctx["pct"]}\u00a0%' + comparison
    return RESET + text_color('percent') + f' {ctx["pct"]}\u00a0%'


def _render_tokens(ctx, opts):
    token_comparison = ctx.get('token_comparison', '')
    if opts.get('fallback') == '1':
        return ctx['token_display'] + token_comparison
    return ctx['token_display']


def _render_directory(ctx, opts):
    cwd = ctx.get('cwd')
    if not cwd:
        return ''
    home = os.path.expanduser('~')
    if cwd.startswith(home):
        cwd_short = '~' + cwd[len(home):]
    else:
        cwd_short = cwd
    return f'   {text_color("cwd")}{cwd_short}'


def _render_git_branch(ctx, opts):
    cwd = ctx.get('cwd')
    if not cwd:
        return ''
    git_branch = get_git_branch(cwd)
    if not git_branch:
        return ''
    if opts.get('hide_default') == '1' and git_branch in ('main', 'master'):
        return ''
    return f'   {BOLD}{text_color("git")}[{git_branch}]'


def _render_usage_5hour(ctx, opts):
    return ctx.get('usage_5hour', '')


def _render_usage_weekly(ctx, opts):
    return ctx.get('usage_weekly', '')


SEGMENT_RENDERERS = {
    'model': _render_model,
    'progress_bar': _render_progress_bar,
    'percentage': _render_percentage,
    'tokens': _render_tokens,
    'directory': _render_directory,
    'git_branch': _render_git_branch,
    'usage_5hour': _render_usage_5hour,
    'usage_weekly': _render_usage_weekly,
}


# =============================================================================
# MAIN STATUS LINE BUILDER
# =============================================================================


def build_progress_bar(
    pct,
    model,
    cwd,
    total_tokens,
    context_limit,
    transcript_tokens=None,
    calc_pct=None,
    usage_5hour='',
    usage_weekly='',
):
    """Build the full status line string"""
    bar_width = max(1, min(128, int(_segment_opts('progress_bar').get('width', '12'))))
    exact_fill = pct * bar_width / 100
    filled = int(exact_fill)
    fraction = exact_fill - filled

    BLOCKS = " ▏▎▍▌▋▊▉█"  # index 0=empty, 8=full

    bar_rgb, bar_256 = get_colors_for_percentage(pct)
    model_color = get_model_colors(model)

    # Build fallback comparison strings (per-segment opts)
    token_comparison = ""
    pct_comparison = ""
    tokens_opts = _segment_opts('tokens')
    pct_opts = _segment_opts('percentage')
    comparisons = []
    show_comparison = False
    if tokens_opts.get('fallback') == '1' and transcript_tokens is not None and total_tokens is not None and total_tokens > 0:
        diff_pct = abs(transcript_tokens - total_tokens) / total_tokens * 100
        if diff_pct > 10:
            comparisons.append(f"{transcript_tokens // 1000}k")
            show_comparison = True
    if pct_opts.get('fallback') == '1' and calc_pct is not None and pct > 0:
        diff_pct = abs(calc_pct - pct) / pct * 100
        if diff_pct > 10:
            comparisons.append(f"{calc_pct}\u00a0%")
            show_comparison = True
    if show_comparison and comparisons:
        theme = THEMES[THEME]
        red_rgb, red_fb = theme["usage_red"]
        red_color = _color(red_rgb, red_fb, is_bg=False)
        combined = f"{red_color}\u00a0{{{'\u00a0'.join(comparisons)}}}"
        # Split comparison parts: token comparison goes with tokens, pct with percentage
        if len(comparisons) == 2:
            token_comparison = f"{red_color}\u00a0{{{comparisons[0]}}}"
            pct_comparison = f"{red_color}\u00a0{{{comparisons[1]}}}"
        elif tokens_opts.get('fallback') == '1' and transcript_tokens is not None and total_tokens is not None and total_tokens > 0:
            diff_pct = abs(transcript_tokens - total_tokens) / total_tokens * 100
            if diff_pct > 10:
                token_comparison = combined
        else:
            pct_comparison = combined

    # Token display (may be None if only API percentage available)
    numbers_color = text_color("numbers")
    if total_tokens is not None:
        token_display = (
            f"{numbers_color}\u00a0({total_tokens // 1000}k/{context_limit // 1000}k)"
        )
    else:
        token_display = f"{numbers_color}\u00a0(--/{context_limit // 1000}k)"

    # Build bar with sub-character precision
    fill_fg = fg_gradient(bar_rgb, bar_256)
    empty_fg_str = fg_empty()
    block_index = round(fraction * 8)

    if block_index == 8:
        filled += 1
        transition = ""
    elif block_index == 0 or filled >= bar_width:
        transition = ""
    else:
        theme = THEMES[THEME]
        empty_rgb, empty_fb = theme["bar_empty"]
        bg_empty = _color(empty_rgb, empty_fb, is_bg=True)
        transition = bg_empty + fill_fg + BLOCKS[block_index]

    empty = bar_width - filled - (1 if transition else 0)

    ctx = {
        'model': model,
        'model_color': model_color,
        'fill_fg': fill_fg,
        'filled': filled,
        'transition': transition,
        'empty_fg_str': empty_fg_str,
        'empty': empty,
        'pct': pct,
        'pct_comparison': pct_comparison,
        'token_display': token_display,
        'token_comparison': token_comparison,
        'cwd': cwd,
        'usage_5hour': usage_5hour,
        'usage_weekly': usage_weekly,
    }

    parts = []
    for name, opts in SEGMENTS:
        renderer = SEGMENT_RENDERERS.get(name)
        if renderer:
            result = renderer(ctx, opts)
            if result:
                parts.append(result)
    parts.append(RESET)

    return "".join(parts)


def build_na_line(model, cwd):
    """Build status line when no usage data available"""
    na_text = f" {text_color('na')}  context size N/A"
    ctx = {
        'model': model,
        'model_color': get_model_colors(model),
        'cwd': cwd,
    }

    session_segments = frozenset(('progress_bar', 'percentage', 'tokens'))
    parts = []
    na_inserted = False
    for name, opts in SEGMENTS:
        if name == 'model':
            parts.append(_render_model(ctx, opts))
        elif name in ('directory', 'git_branch'):
            if not na_inserted:
                parts.append(na_text)
                na_inserted = True
            renderer = SEGMENT_RENDERERS.get(name)
            if renderer:
                result = renderer(ctx, opts)
                if result:
                    parts.append(result)
        elif name in session_segments and not na_inserted:
            parts.append(na_text)
            na_inserted = True

    if not na_inserted:
        parts.append(na_text)

    parts.append(RESET)
    return "".join(parts)


# =============================================================================
# DEMO MODE
# =============================================================================


def show_usage_demo():
    """Demo mode to show usage indicator with mock data"""
    from datetime import timedelta

    now = datetime.now().astimezone()

    # Create mock usage data with different scenarios (utilization is 0-100%)
    # Forward-looking ratio = remaining_budget / remaining_time
    # ratio >= 1/0.75: light, >= 1.0: green, >= 0.75: orange, < 0.75: red
    scenarios = [
        (
            "Light - well ahead (ratio >= 1.33)",
            {
                # 10% used, 2h elapsed of 5h -> 90% budget, 60% time left -> ratio = 1.5
                "five_hour": {
                    "utilization": 10,
                    "resets_at": (now + timedelta(hours=3)).isoformat(),
                },
                # 5% used, 2d elapsed of 7d -> 95% budget, 71% time left -> ratio = 1.33
                "seven_day": {
                    "utilization": 5,
                    "resets_at": (now + timedelta(days=5)).isoformat(),
                },
            },
        ),
        (
            "Green - on track (ratio ~1.0)",
            {
                # 20% used, 1h elapsed of 5h -> 80% budget, 80% time left -> ratio = 1.0
                "five_hour": {
                    "utilization": 20,
                    "resets_at": (now + timedelta(hours=4)).isoformat(),
                },
                # 14% used, 1d elapsed of 7d -> 86% budget, 86% time left -> ratio = 1.0
                "seven_day": {
                    "utilization": 14,
                    "resets_at": (now + timedelta(days=6)).isoformat(),
                },
            },
        ),
        (
            "Yellow - tighter runway (ratio ~0.83)",
            {
                # 50% used, 2h elapsed of 5h -> 50% budget, 60% time left -> ratio = 0.83
                "five_hour": {
                    "utilization": 50,
                    "resets_at": (now + timedelta(hours=3)).isoformat(),
                },
                "seven_day": {
                    "utilization": 14,
                    "resets_at": (now + timedelta(days=6)).isoformat(),
                },
            },
        ),
        (
            "Red - running out (ratio < 0.75)",
            {
                # 80% used, 2h elapsed of 5h -> 20% budget, 60% time left -> ratio = 0.33
                "five_hour": {
                    "utilization": 80,
                    "resets_at": (now + timedelta(hours=3)).isoformat(),
                },
                # 60% used, 2d elapsed of 7d -> 40% budget, 71% time left -> ratio = 0.56
                "seven_day": {
                    "utilization": 60,
                    "resets_at": (now + timedelta(days=5)).isoformat(),
                },
            },
        ),
    ]

    print("Usage Indicator Demo (forward-looking ratio = remaining budget / remaining time):")
    print("=" * 75)
    print("  ratio >= 1.33: light | 1.0-1.33: green | 0.75-1.0: yellow | < 0.75: red")
    print()

    global SEGMENTS
    original_segments = SEGMENTS

    for name, mock_data in scenarios:
        # Temporarily set vertical gauge for demo
        SEGMENTS = [
            ('usage_5hour', {'gauge': 'vertical', 'width': '4'}),
            ('usage_weekly', {'gauge': 'vertical', 'width': '4'}),
        ]
        parts = format_usage_indicators(mock_data)
        vertical = parts['usage_5hour'] + parts['usage_weekly']
        # Temporarily set blocks gauge for demo
        SEGMENTS = [
            ('usage_5hour', {'gauge': 'blocks', 'width': '4'}),
            ('usage_weekly', {'gauge': 'blocks', 'width': '4'}),
        ]
        parts = format_usage_indicators(mock_data)
        blocks = parts['usage_5hour'] + parts['usage_weekly']
        print(f"{name}:")
        print(f"  vertical:{vertical}{RESET}")
        print(f"  blocks:  {blocks}{RESET}")
        print()

    SEGMENTS = original_segments


def show_scale_demo(mode="animate"):
    """Demo mode to show color gradient"""

    def show_bar(pct):
        BLOCKS = " ▏▎▍▌▋▊▉█"
        bar_width = max(1, min(128, int(_segment_opts('progress_bar').get('width', '12'))))
        bar_length = bar_width
        exact_fill = pct * bar_width / 100
        filled = int(exact_fill)
        fraction = exact_fill - filled
        bar_rgb, bar_256 = get_colors_for_percentage(pct)
        fill_fg = fg_gradient(bar_rgb, bar_256)
        empty_fg_str = fg_empty()
        block_index = round(fraction * 8)

        if block_index == 8:
            filled += 1
            transition = ""
        elif block_index == 0 or filled >= bar_length:
            transition = ""
        else:
            theme = THEMES[THEME]
            empty_rgb, empty_fb = theme["bar_empty"]
            bg_empty = _color(empty_rgb, empty_fb, is_bg=True)
            transition = bg_empty + fill_fg + BLOCKS[block_index]

        empty = bar_length - filled - (1 if transition else 0)
        bar = (
            fill_fg
            + "█" * filled
            + transition
            + RESET
            + empty_fg_str
            + "█" * empty
            + RESET
        )
        return bar

    if mode == "animate":
        try:
            while True:
                for pct in range(101):
                    print(f"\r{pct:3d}%: {show_bar(pct)}", end="", flush=True)
                    time.sleep(0.1)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()
    elif mode in ("min", "max", "mid"):
        ranges = [
            (0, 9),
            (10, 19),
            (20, 29),
            (30, 39),
            (40, 49),
            (50, 59),
            (60, 69),
            (70, 79),
            (80, 89),
            (90, 100),
        ]
        print(f"Color Scale Demo ({mode} value):")
        print()
        for lo, hi in ranges:
            pct = lo if mode == "min" else hi if mode == "max" else (lo + hi) // 2
            print(f"{lo:3d}-{hi:3d}%: {show_bar(pct)}")
    else:
        print(f"Error: Invalid mode '{mode}'. Use: min, max, mid, or animate")
        sys.exit(1)


def show_gauge_sweep_demo():
    """Animated demo: both gauge types sweeping through full ratio range."""
    CL = "\033[K"

    # Sweep: 2.0 → 0.0 → 2.0 (continuous loop)
    n = 100
    steps = []
    for i in range(n, -1, -1):
        steps.append(i * 2.0 / n)
    for i in range(1, n):
        steps.append(i * 2.0 / n)

    num_lines = 3  # blank, content, blank

    for _ in range(num_lines):
        print()

    try:
        while True:
            for ratio in steps:
                if ratio >= 1 / 0.75:
                    zone = "light"
                elif ratio >= 1.0:
                    zone = "green"
                elif ratio >= 0.75:
                    zone = "yellow"
                else:
                    zone = "red"

                vertical = get_usage_gauge(ratio)
                blocks = get_usage_gauge_blocks(ratio, gauge_width=8)

                sys.stdout.write(f"\033[{num_lines}A")
                sys.stdout.write(f"{CL}\n")
                label = f"ratio: {ratio:.2f}  ({zone})"
                sys.stdout.write(
                    f"  {vertical}{RESET}    "
                    f"{label:<24s}    "
                    f"{blocks}{RESET}{CL}\n"
                )
                sys.stdout.write(f"{CL}\n")
                sys.stdout.flush()
                time.sleep(0.03)
    except KeyboardInterrupt:
        print()


def show_usage_principle_demo():
    """Animated demo: same usage % at different time positions in 5h window."""
    CL = "\033[K"
    PAD = " " * 10
    NBSP = "\u00a0"

    window_min = 300  # 5 hours
    start_t = 10
    end_t = 290
    window_start_h = 10  # window is 10:00 – 15:00
    reset_label = "15:00"

    # Precompute monotonic usage curve with breaks and varying rate
    base_rate = 100 / window_min
    osc_P = 100
    breaks = [(75, 95), (185, 210)]  # "not using" periods
    osc_curve = []  # (usage, rate) per minute
    usage = 0.0
    for step_t in range(window_min + 1):
        in_break = any(s <= step_t < e for s, e in breaks)
        if in_break:
            rate = 0.0
        else:
            rate = base_rate * (1 + 0.8 * math.sin(2 * math.pi * step_t / osc_P))
        osc_curve.append((min(100, usage), rate))
        usage += rate

    # header + 3 x (blank + label + gauges) = 10 lines
    num_lines = 10

    for _ in range(num_lines):
        print()

    def gauge_line(ratio, remaining_pct, reset_label):
        color = get_usage_color(ratio)
        v = get_usage_gauge(ratio)
        b = get_usage_gauge_blocks(ratio, gauge_width=8)
        pct_str = str(remaining_pct).rjust(3).replace(' ', NBSP)
        return (
            f"{PAD}{v}{RESET}  {b}{RESET}"
            f" {color}{pct_str}{NBSP}%{NBSP}\u2192{NBSP}{reset_label}{RESET}"
        )

    try:
        while True:
            for t in range(start_t, end_t + 1, 2):
                clock_h, clock_m = divmod(window_start_h * 60 + t, 60)
                rh, rm = divmod(window_min - t, 60)
                remaining_time_pct = (window_min - t) / window_min * 100

                sys.stdout.write(f"\033[{num_lines}A")

                # Shared header
                sys.stdout.write(
                    f"5-hour window  10:00\u201315:00   "
                    f"now {clock_h}:{clock_m:02d}  ({rh}:{rm:02d} left){CL}\n"
                )

                # Fixed 10% usage
                ratio_10 = 90 / remaining_time_pct if remaining_time_pct > 0.1 else 2.0
                sys.stdout.write(f"{CL}\n")
                sys.stdout.write(f"10% usage{CL}\n")
                sys.stdout.write(f"{gauge_line(ratio_10, 90, reset_label)}{CL}\n")

                # Fixed 90% usage
                ratio_90 = 10 / remaining_time_pct if remaining_time_pct > 0.1 else 2.0
                sys.stdout.write(f"{CL}\n")
                sys.stdout.write(f"90% usage{CL}\n")
                sys.stdout.write(f"{gauge_line(ratio_90, 10, reset_label)}{CL}\n")

                # Monotonically rising usage with varying rate and breaks
                osc_usage, osc_rate = osc_curve[t]
                osc_remaining_pct = round(100 - osc_usage)
                if remaining_time_pct > 0.1:
                    osc_ratio = osc_remaining_pct / remaining_time_pct
                else:
                    osc_ratio = 2.0 if osc_remaining_pct > 0 else 1.0
                if osc_rate == 0:
                    intensity = "not using"
                elif osc_rate > base_rate:
                    intensity = "more intensive usage now"
                else:
                    intensity = "less intensive usage now"
                sys.stdout.write(f"{CL}\n")
                sys.stdout.write(f"{round(osc_usage):2d}% usage — {intensity}{CL}\n")
                sys.stdout.write(f"{gauge_line(osc_ratio, osc_remaining_pct, reset_label)}{CL}\n")

                sys.stdout.flush()
                time.sleep(0.1)
    except KeyboardInterrupt:
        print()


# =============================================================================
# MAIN
# =============================================================================


def main():
    # Check theme is configured
    if THEME not in THEMES:
        # Yellow text on red bg, then red text on yellow bg
        print(
            f"\033[48;5;196m\033[38;5;220m\033[1m PLEASE SET THEME to 'dark' or 'light' in claude-code-status-line.py \033[0m"
        )
        print(
            f"\033[48;5;220m\033[38;5;196m\033[1m PLEASE SET THEME to 'dark' or 'light' in claude-code-status-line.py \033[0m"
        )
        return

    # Handle demo modes
    if len(sys.argv) > 1:
        if sys.argv[1] == "--show-scale":
            show_scale_demo(sys.argv[2] if len(sys.argv) > 2 else "animate")
            return
        if sys.argv[1] == "--test-usage":
            show_usage_demo()
            return
        if sys.argv[1] == "--test-gauge":
            show_gauge_sweep_demo()
            return
        if sys.argv[1] == "--test-principle":
            show_usage_principle_demo()
            return

    # Read and parse JSON input
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("statusline: invalid JSON input", file=sys.stderr)
        return

    model = data.get("model", {}).get("display_name", "Claude")
    cwd = data.get("cwd", "")

    # Get context window info
    context_window = data.get("context_window", {})
    context_limit = context_window.get("context_window_size", 200000)
    used_percentage = context_window.get("used_percentage")
    current_usage = context_window.get("current_usage")

    # Calculate total tokens for display purposes
    if current_usage:
        total_tokens = (
            current_usage.get("input_tokens", 0)
            + current_usage.get("cache_creation_input_tokens", 0)
            + current_usage.get("cache_read_input_tokens", 0)
            + current_usage.get("output_tokens", 0)
        )
    else:
        total_tokens = None

    # Calculate percentage from tokens (for comparison)
    if total_tokens and total_tokens > 0:
        calc_pct = min(100, int(total_tokens * 100 / context_limit))
    else:
        calc_pct = None

    # Use API percentage, fall back to calculated
    if used_percentage is not None:
        pct = int(used_percentage)
    elif calc_pct is not None:
        pct = calc_pct
    else:
        print(build_na_line(model, cwd))
        return

    # Get transcript tokens for comparison
    transcript_path = data.get("transcript_path")
    transcript_tokens = get_tokens_from_transcript(transcript_path)

    # Get usage limits indicators
    usage_data = fetch_usage_data()
    usage_parts = format_usage_indicators(usage_data)

    print(
        build_progress_bar(
            pct,
            model,
            cwd,
            total_tokens,
            context_limit,
            transcript_tokens,
            calc_pct,
            usage_5hour=usage_parts['usage_5hour'],
            usage_weekly=usage_parts['usage_weekly'],
        )
    )


if __name__ == "__main__":
    main()
