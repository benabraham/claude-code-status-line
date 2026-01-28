# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Python statusline script for Claude Code CLI. Displays context window usage, model info, budget tracking, and git status as a colored single-line bar. Stdlib only (json, os, subprocess, sys, tempfile, time, datetime). Custom themes require `tomllib` (Python 3.11+ stdlib) or optional `tomli` package.

## Running and Testing

There is no build step, test suite, or linter. The script is a standalone executable.

```bash
# Demo: animated color gradient sweep
./claude-code-status-line.py --show-scale

# Demo: static gradient views (min/mid/max per range)
./claude-code-status-line.py --show-scale mid

# Demo: usage indicator scenarios
./claude-code-status-line.py --test-usage

# Demo: gauge sweep (both vertical and blocks, ratio 2.0 → 0.0 → 2.0)
./claude-code-status-line.py --test-gauge

# Demo: usage principle (10%, 90%, and varying usage in 5-hour window)
./claude-code-status-line.py --test-principle

# Normal operation: receives JSON on stdin from Claude Code
echo '{"model":"claude-sonnet-4-20250514","cwd":"/tmp","contextWindow":{"used_percentage":42}}' | ./claude-code-status-line.py
```

## Architecture

The script is a single pipeline: **JSON stdin → parse → compute → render ANSI line → stdout**.

Key sections in `claude-code-status-line.py` (~1,340 lines):

- **Lines 34-115**: Configuration — `SL_THEME`/`SL_USAGE_CACHE_DURATION`/`SL_THEME_FILE` globals, then `SL_SEGMENTS` parsing (`_parse_segments`, `_has_segment`, `_segment_opts`). Width values capped at 128.
- **Lines ~116-155**: Color conversion (`hex_to_rgb`, `hex_to_256`) with hex length validation, and truecolor/256-color terminal detection via `COLORTERM` env var
- **Lines ~156-340**: Theme system — `THEMES` dict (dark/light, Nord-inspired), `_load_custom_theme()` loads optional `~/.claude/claude-code-theme.toml` via `tomllib`
- **Lines ~456**: `get_git_branch()` — subprocess call to `git branch --show-current`, strips ESC characters from output
- **Lines ~559**: `fetch_usage_data()` — OAuth API call via `curl` subprocess, cached atomically to `~/.claude/.usage_cache.json` for `USAGE_CACHE_DURATION` seconds
- **Lines ~626-753**: Usage gauge rendering — vertical (block chars ▁▂▃▄▅▆▇█) and horizontal blocks styles with forward-looking ratio logic
- **Lines ~756**: `format_usage_indicators()` — returns dict with per-window usage strings
- **Lines ~849-917**: Segment renderers — `_render_model`, `_render_progress_bar`, `_render_percentage`, `_render_tokens`, `_render_directory`, `_render_git_branch`, `_render_usage_5hour`, `_render_usage_weekly` + `SEGMENT_RENDERERS` dict
- **Lines ~925**: `build_progress_bar()` — builds ctx dict, iterates SEGMENTS calling renderers
- **Lines ~1036**: `build_na_line()` — iterates SEGMENTS for N/A display
- **Lines ~1253**: `main()` — entry point, handles demo modes and normal stdin flow

## Code Patterns

- **Segment system**: `SL_SEGMENTS` env var controls visibility, order, and per-segment options. Parsed into `[(name, {opts}), ...]` list. Each segment has a renderer function receiving `(ctx, opts)`. Unknown names silently filtered.
- **Configuration**: global settings via `SL_THEME`, `SL_USAGE_CACHE_DURATION`, `SL_THEME_FILE`. All per-segment config (bar width, gauge style, fallback display, hide default branch) via colon-separated options in `SL_SEGMENTS`.
- **Color handling**: hex colors converted to both truecolor RGB escape sequences and 256-color fallbacks. `hex_to_rgb()` validates 6-char length; `hex_to_256()` falls back to color 0 on invalid input. Theme colors are always hex strings; conversion happens at render time.
- **Custom themes**: loaded via `tomllib` from a TOML file (Python 3.11+, `tomli` fallback), only the defined keys override the base theme. Silently skipped if no TOML parser available.
- **Progress bar precision**: Unicode fractional blocks (▏▎▍▌▋▊▉█) for sub-character precision with gradient color interpolation across 10 thresholds.
- **Input validation**: OAuth token characters allowlisted before HTTP use. Git branch names stripped of ESC chars. Segment widths capped at 128. Hex colors length-checked. Usage ratio guarded against near-zero divisor.
- **Credential sources**: macOS Keychain (`security` command) → `~/.claude/.credentials.json` fallback.
- **Cache writes**: atomic via `tempfile.mkstemp()` + `os.replace()` with temp file cleanup on failure.
- **Data source fallbacks**: API `used_percentage` is primary; transcript token parsing is fallback. Discrepancies >10% shown in red curly braces when `percentage:fallback=1` / `tokens:fallback=1`.
- **No type hints** per project convention — uses f-strings throughout.
