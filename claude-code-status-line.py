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
import os
import subprocess
import sys
import time
from datetime import datetime

# =============================================================================
# CONFIGURATION — override any setting via environment variables (SL_ prefix)
# Example: SL_THEME=light SL_SHOW_GIT_BRANCH=0 ~/.claude/claude-code-status-line.py
# =============================================================================


def _env_str(key, default):
    return os.environ.get(f"SL_{key}", default)


def _env_int(key, default):
    return int(os.environ.get(f"SL_{key}", default))


def _env_bool(key, default):
    val = os.environ.get(f"SL_{key}")
    if val is None:
        return default
    return val.lower() not in ("0", "false", "no", "off")


SESSION_PROGRESS_BAR_WIDTH = _env_int("SESSION_PROGRESS_BAR_WIDTH", 12)
THEME = _env_str("THEME", "dark")
USAGE_LEFT_GAUGE_STYLE = _env_str("USAGE_LEFT_GAUGE_STYLE", "blocks")
USAGE_LEFT_BLOCK_GAUGE_WIDTH = _env_int("USAGE_LEFT_BLOCK_GAUGE_WIDTH", 4)

SHOW_MODEL_NAME = _env_bool("SHOW_MODEL_NAME", True)
SHOW_SESSION_PROGRESS_BAR = _env_bool("SHOW_SESSION_PROGRESS_BAR", True)
SHOW_SESSION_PERCENTAGE = _env_bool("SHOW_SESSION_PERCENTAGE", True)
SHOW_SESSION_TOKENS = _env_bool("SHOW_SESSION_TOKENS", True)
SHOW_CURRENT_DIR = _env_bool("SHOW_CURRENT_DIR", True)
SHOW_GIT_BRANCH = _env_bool("SHOW_GIT_BRANCH", True)
HIDE_DEFAULT_BRANCH = _env_bool("HIDE_DEFAULT_BRANCH", True)
SHOW_5H_USAGE_LEFT = _env_bool("SHOW_5H_USAGE_LEFT", True)
SHOW_WEEKLY_USAGE_LEFT = _env_bool("SHOW_WEEKLY_USAGE_LEFT", True)
SHOW_FALLBACK_INFO = _env_bool("SHOW_FALLBACK_INFO", True)

USAGE_CACHE_DURATION = _env_int("USAGE_CACHE_DURATION", 300)

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

# =============================================================================
# COLOR SUPPORT DETECTION & CONVERSION
# =============================================================================


def hex_to_rgb(hex_color):
    """Convert '#RRGGBB' hex string to (R, G, B) tuple"""
    if hex_color is None:
        return None
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


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
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def get_cwd_suffix(cwd):
    """Format cwd and git branch for display"""
    if not cwd:
        return ""

    suffix = ""

    if SHOW_CURRENT_DIR:
        # Shorten home directory to ~
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd_short = "~" + cwd[len(home) :]
        else:
            cwd_short = cwd
        suffix += f"   {text_color('cwd')}{cwd_short}"

    if SHOW_GIT_BRANCH:
        git_branch = get_git_branch(cwd)
        if git_branch:
            if not (HIDE_DEFAULT_BRANCH and git_branch in ("main", "master")):
                suffix += f"   {BOLD}{text_color('git')}[{git_branch}]"

    return suffix


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

    # Get OAuth token
    token = get_oauth_token()
    if not token:
        return None

    # Fetch from API using curl
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-f",
                "-H",
                "Accept: application/json",
                "-H",
                "Content-Type: application/json",
                "-H",
                "User-Agent: claude-code/2.0.32",
                "-H",
                "anthropic-beta: oauth-2025-04-20",
                "-H",
                f"Authorization: Bearer {token}",
                "https://api.anthropic.com/api/oauth/usage",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)

        # Cache the result
        try:
            with open(USAGE_CACHE_PATH, "w") as f:
                json.dump({"timestamp": time.time(), "data": data}, f)
        except IOError:
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


def get_usage_gauge_blocks(ratio):
    """Horizontal gauge using partial blocks (width set by USAGE_LEFT_BLOCK_GAUGE_WIDTH).

    Left half: green (shows how far ahead, fills right-to-left from center).
    Right half: orange/red (shows how far behind, fills left-to-right from center).
    - ratio >= 1.0: green fills left half
    - ratio < 1.0: orange fills right half
    - ratio < 0.75: red instead of orange
    """
    theme = THEMES[THEME]
    BLOCKS = " ▏▎▍▌▋▊▉█"
    half = USAGE_LEFT_BLOCK_GAUGE_WIDTH // 2
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


def format_usage_indicator(usage_data):
    """Format usage indicator for status line."""
    if usage_data is None:
        return f"   {text_color('na')}usage: N/A"
    if not usage_data:
        return ""

    indicators = []

    # Define limit types to process: (key, window_hours, time_format, show_flag)
    # Use NBSP (\u00a0) between day and time for weekly
    limit_configs = [
        ("five_hour", 5, "%H:%M", SHOW_5H_USAGE_LEFT),
        ("seven_day", 7 * 24, "%a\u00a0%H:%M", SHOW_WEEKLY_USAGE_LEFT),
    ]

    for key, window_hours, time_fmt, show_flag in limit_configs:
        if not show_flag:
            continue
        limit = usage_data.get(key)
        if not limit:
            continue

        utilization_pct = limit.get("utilization", 0)  # 0-100 percentage
        resets_at = limit.get("resets_at")

        if not resets_at:
            continue

        # Parse reset time
        try:
            reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        except ValueError:
            continue

        now = datetime.now(reset_dt.tzinfo)
        remaining_pct = max(0, int(100 - utilization_pct))
        reset_label = reset_dt.astimezone().strftime(time_fmt)

        # Calculate time elapsed in window
        window_seconds = window_hours * 3600
        window_start = reset_dt.timestamp() - window_seconds
        elapsed_seconds = now.timestamp() - window_start
        time_elapsed_pct = max(0, min(100, (elapsed_seconds / window_seconds) * 100))

        # Forward-looking ratio: remaining_budget / remaining_time
        # 1.0 = can sustain 100/window_days per day until reset (green)
        # < 1.0 = will run out before reset at sustainable rate
        remaining_budget_pct = max(0, 100 - utilization_pct)
        remaining_time_pct = max(0, 100 - time_elapsed_pct)
        if remaining_time_pct > 0:
            ratio = remaining_budget_pct / remaining_time_pct
        elif remaining_budget_pct > 0:
            ratio = 2.0  # Window ending with budget left
        else:
            ratio = 1.0  # Window and budget ending together

        color = get_usage_color(ratio)

        # Override text color for 5h window based on absolute remaining budget
        # Only override to a worse color than ratio already gives
        if key == "five_hour":
            if remaining_pct <= 5:
                color = get_usage_color(0)  # red (always worse or equal)
            elif remaining_pct <= 10 and ratio >= 0.75:
                color = get_usage_color(0.8)  # orange (only if ratio isn't already red)

        if USAGE_LEFT_GAUGE_STYLE == "none":
            gauge = ""
        elif USAGE_LEFT_GAUGE_STYLE == "blocks":
            gauge = get_usage_gauge_blocks(ratio)
        else:
            gauge = get_usage_gauge(ratio)
        gauge_part = f"{gauge}\u00a0" if gauge else ""
        indicators.append(
            f"{gauge_part}{color}{remaining_pct}\u00a0%\u00a0→\u00a0{reset_label}"
        )

    if not indicators:
        return ""

    return f"   {'\u00a0\u00a0'.join(indicators)}"


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
    usage_indicator="",
):
    """Build the full status line string"""
    bar_length = SESSION_PROGRESS_BAR_WIDTH
    exact_fill = pct * SESSION_PROGRESS_BAR_WIDTH / 100
    filled = int(exact_fill)
    fraction = exact_fill - filled

    BLOCKS = " ▏▎▍▌▋▊▉█"  # index 0=empty, 8=full

    bar_rgb, bar_256 = get_colors_for_percentage(pct)
    model_color = get_model_colors(model)

    # Build comparison suffix - only show if values differ by more than 10%
    comparisons = []
    show_comparison = False
    if SHOW_FALLBACK_INFO and transcript_tokens is not None and total_tokens is not None and total_tokens > 0:
        diff_pct = abs(transcript_tokens - total_tokens) / total_tokens * 100
        if diff_pct > 10:
            comparisons.append(f"{transcript_tokens // 1000}k")
            show_comparison = True
    if SHOW_FALLBACK_INFO and calc_pct is not None and pct > 0:
        diff_pct = abs(calc_pct - pct) / pct * 100
        if diff_pct > 10:
            comparisons.append(f"{calc_pct}\u00a0%")
            show_comparison = True
    if show_comparison and comparisons:
        theme = THEMES[THEME]
        red_rgb, red_fb = theme["usage_red"]
        red_color = _color(red_rgb, red_fb, is_bg=False)
        comparison = f"{red_color}\u00a0{{{'\u00a0'.join(comparisons)}}}"
    else:
        comparison = ""

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
    elif block_index == 0 or filled >= bar_length:
        transition = ""
    else:
        theme = THEMES[THEME]
        empty_rgb, empty_fb = theme["bar_empty"]
        bg_empty = _color(empty_rgb, empty_fb, is_bg=True)
        transition = bg_empty + fill_fg + BLOCKS[block_index]

    empty = bar_length - filled - (1 if transition else 0)

    parts = []
    if SHOW_MODEL_NAME:
        parts.append(model_color + center_text(model) + RESET)
    if SHOW_SESSION_PROGRESS_BAR:
        parts.append(fill_fg + "█" * filled)
        parts.append(transition)
        parts.append(RESET + empty_fg_str + "█" * empty)
    if SHOW_SESSION_PERCENTAGE:
        parts.append(RESET + text_color("percent"))
        parts.append(f" {pct}\u00a0%")
    if SHOW_SESSION_TOKENS:
        parts.append(token_display)
        parts.append(comparison)
    parts.append(get_cwd_suffix(cwd))
    parts.append(usage_indicator)
    parts.append(RESET)

    return "".join(parts)


def build_na_line(model, cwd):
    """Build status line when no usage data available"""
    parts = []
    if SHOW_MODEL_NAME:
        model_color = get_model_colors(model)
        parts.append(f"{model_color}{center_text(model)}{RESET}")
    parts.append(f" {text_color('na')}  context size N/A")
    parts.append(get_cwd_suffix(cwd))
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

    global USAGE_LEFT_GAUGE_STYLE
    original_style = USAGE_LEFT_GAUGE_STYLE

    for name, mock_data in scenarios:
        USAGE_LEFT_GAUGE_STYLE = "vertical"
        vertical = format_usage_indicator(mock_data)
        USAGE_LEFT_GAUGE_STYLE = "blocks"
        blocks = format_usage_indicator(mock_data)
        print(f"{name}:")
        print(f"  vertical:{vertical}{RESET}")
        print(f"  blocks:  {blocks}{RESET}")
        print()

    USAGE_LEFT_GAUGE_STYLE = original_style


def show_scale_demo(mode="animate"):
    """Demo mode to show color gradient"""

    def show_bar(pct):
        BLOCKS = " ▏▎▍▌▋▊▉█"
        bar_length = SESSION_PROGRESS_BAR_WIDTH
        exact_fill = pct * SESSION_PROGRESS_BAR_WIDTH / 100
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

    # Get usage limits indicator
    usage_data = fetch_usage_data()
    usage_indicator = format_usage_indicator(usage_data)

    print(
        build_progress_bar(
            pct,
            model,
            cwd,
            total_tokens,
            context_limit,
            transcript_tokens,
            calc_pct,
            usage_indicator,
        )
    )


if __name__ == "__main__":
    main()
