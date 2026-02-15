# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Python statusline script for Claude Code CLI. Displays context window usage, model info, budget tracking, git status, and update notifications as a colored status bar (single or multi-line). Stdlib only (json, os, subprocess, sys, tempfile, time, datetime). Custom themes require `tomllib` (Python 3.11+ stdlib) or optional `tomli` package.

## Running and Testing

There is no build step, test suite, or linter. The script is a standalone executable.

```bash
# Demo: animated color gradient sweep
./claude-code-status-line.py --demo-scale

# Demo: static gradient views (min/mid/max per range)
./claude-code-status-line.py --demo-scale mid

# Demo: usage indicator scenarios
./claude-code-status-line.py --demo-usage

# Demo: gauge sweep (both vertical and blocks, ratio 2.0 → 0.0 → 2.0)
./claude-code-status-line.py --demo-gauge

# Demo: usage principle (10%, 90%, and varying usage in 5-hour window)
./claude-code-status-line.py --demo-principle

# Normal operation: receives JSON on stdin from Claude Code
echo '{"model":"claude-sonnet-4-20250514","cwd":"/tmp","contextWindow":{"used_percentage":42}}' | ./claude-code-status-line.py
```

## Architecture

The script is a single pipeline: **JSON stdin → parse → compute → render ANSI line → stdout**.

Key sections in `claude-code-status-line.py` (~2,200 lines):

- **Lines 34-115**: Configuration — `SL_THEME`/`SL_USAGE_CACHE_DURATION`/`SL_UPDATE_CACHE_DURATION`/`SL_UPDATE_RETRY_DURATION`/`SL_UPDATE_CUSTOM_RETRY_DURATION`/`SL_UPDATE_VERSION_CMD`/`SL_UPDATE_VERSION_SOURCE`/`SL_THEME_FILE` globals, then `SL_SEGMENTS` parsing (`_parse_segments`, `_has_segment`, `_segment_opts`). Width values capped at 128.
- **Lines ~116-165**: Color conversion (`hex_to_rgb`, `hex_to_256`) with hex length validation, and truecolor/256-color terminal detection via `COLORTERM` env var
- **Lines ~170-355**: Theme system — `THEMES` dict (dark/light, Nord-inspired), `_load_custom_theme()` loads optional `~/.claude/claude-code-theme.toml` via `tomllib`
- **Lines ~468**: `get_git_branch()` — subprocess call to `git branch --show-current`, strips ESC characters from output
- **Lines ~497**: `get_git_status()` — collects working directory state (staged/modified/deleted/renamed/untracked/conflicted), stash count, and ahead/behind status via `git status --porcelain=v1`, `git stash list`, and `git rev-list`
- **Lines ~571**: `fetch_usage_data()` — OAuth API call via `curl` subprocess, cached atomically to `~/.claude/.usage_cache.json` for `USAGE_CACHE_DURATION` seconds
- **Lines ~639-746**: Update checker — `get_installed_version()` runs `claude --version`, `fetch_latest_version()` queries npm registry with caching to `~/.claude/.update_cache.json`, `check_for_update()` compares versions via `parse_semver()`
- **Lines ~749-870**: Usage gauge rendering — vertical (block chars ▁▂▃▄▅▆▇█) and horizontal blocks styles with forward-looking ratio logic
- **Lines ~872**: `format_usage_indicators()` — returns dict with per-window usage strings
- **Lines ~1183**: `_format_duration()` / `_format_duration_compact()` — round durations for burndown; default uses rounded single-unit (`3 d`, `8 h`), compact uses compound no-space form (`5d2h30m`)
- **Lines ~1228**: `_format_burndown()` — three-mode burndown message with `verbosity` param (`default`/`short`): Soon (<1h to depletion), Pace (>=48h, shows pace warning), Countdown (<48h, shows absolute time left)
- **Lines ~1125-1220**: Segment renderers — `_render_model`, `_render_progress_bar`, `_render_percentage`, `_render_tokens`, `_render_directory`, `_render_git_branch`, `_render_git_status`, `_render_usage_5hour`, `_render_usage_weekly`, `_render_usage_burndown`, `_render_update`, `_render_context_na_message`, `_render_new_line` + `SEGMENT_RENDERERS` dict
- **Lines ~1530**: `_join_parts()` — joins segment parts with newline-aware flush-left behavior for multi-line layouts
- **Lines ~1547**: `build_progress_bar()` — builds ctx dict, iterates SEGMENTS calling renderers, uses `_join_parts`
- **Lines ~1664**: `build_na_line()` — builds N/A display with `na_mode` context flag, skips session segments
- **Lines ~2086**: `main()` — entry point, handles demo modes and normal stdin flow

## Code Patterns

- **Segment system**: `SL_SEGMENTS` env var controls visibility, order, and per-segment options. Parsed into `[(name, {opts}), ...]` list. Each segment has a renderer function receiving `(ctx, opts)`. Unknown names silently filtered. Special `new_line` segment enables multi-line layouts; `context_na_message` shows N/A text only when context data unavailable; `usage_burndown` adapts to position in weekly window with `verbosity` option (`default` or `short`). Three modes with example output:
  - **Soon** (<1h left): default `"may run out soon but renew 1440 m away"`, short `"out soon, renew 1440m away"`
  - **Pace** (>=48h left): default `"may run out about 3 d sooner"`, short `"out ~ 3d sooner"`
  - **Countdown** (<48h left): default `"about 8 h usage left then 1 d to renew"`, short `"~ 8h left -> 1d to renew"`
  - Countdown omits renewal gap when early <= 1h: default `"about 8 h usage left"`, short `"~ 8h left"`
  - **Relevance filter**: burndown is suppressed when the predicted "sooner" gap is too small relative to remaining time, using a power curve `days_remaining^coeff` (in hours). This avoids noisy predictions early in the window. Config: `usage_burndown:coeff=1.4` (default). At 6.5 days left requires ~13h sooner, at 1 day ~1h, at 0.5 days ~24min.
  - Config: `usage_burndown:verbosity=short:coeff=1.4`. Short uses compact compound durations (`5d2h30m`), `~` instead of `about`, `->` instead of `then`, drops `usage`, `out ~` instead of `may run out about`; `git_status` shows working directory state using symbols: `+` staged, `!` modified, `x` deleted, `r` renamed, `?` untracked, `=` conflicted, `$` stashed, `>` ahead, `<` behind, `<>` diverged.
- **Configuration**: global settings via `SL_THEME`, `SL_USAGE_CACHE_DURATION`, `SL_UPDATE_CACHE_DURATION`, `SL_UPDATE_RETRY_DURATION`, `SL_UPDATE_CUSTOM_RETRY_DURATION`, `SL_UPDATE_VERSION_CMD`, `SL_UPDATE_VERSION_SOURCE`, `SL_SHOW_STATUSLINE_UPDATE`, `SL_THEME_FILE`. All per-segment config (bar width, gauge style, fallback display, hide default branch, basename-only directory) via colon-separated options in `SL_SEGMENTS`.
- **Update checker**: fetches latest version from npm registry (`@anthropic-ai/claude-code`) or custom command (`SL_UPDATE_VERSION_CMD`), compares with `claude --version` output. Custom command retries 3 times with 1s delay, then falls back to npm. Returns `(version, source)` tuple where source is `npm`, `custom`, or `npm_fallback`. Cached to `~/.claude/.update_cache.json` — success cached for `UPDATE_CACHE_DURATION` (1h), custom source failures retry after `UPDATE_CUSTOM_RETRY_DURATION` (2min), total failures retry after `UPDATE_RETRY_DURATION` (10min). Falls back to stale cache when offline.
- **Self-update**: `--self-update` flag downloads latest version from GitHub and replaces the script atomically. Status line update notifications appear on a separate line below the main output with the update command. Controlled by `SL_SHOW_STATUSLINE_UPDATE` (default on).
- **Color handling**: hex colors converted to both truecolor RGB escape sequences and 256-color fallbacks. `hex_to_rgb()` validates 6-char length; `hex_to_256()` falls back to color 0 on invalid input. Theme colors are always hex strings; conversion happens at render time.
- **Custom themes**: loaded via `tomllib` from a TOML file (Python 3.11+, `tomli` fallback), only the defined keys override the base theme. Silently skipped if no TOML parser available.
- **Progress bar precision**: Unicode fractional blocks (▏▎▍▌▋▊▉█) for sub-character precision with gradient color interpolation across 10 thresholds.
- **Input validation**: OAuth token characters allowlisted before HTTP use. Git branch names stripped of ESC chars. Segment widths capped at 128. Hex colors length-checked. Usage ratio guarded against near-zero divisor.
- **Credential sources**: macOS Keychain (`security` command) → `~/.claude/.credentials.json` fallback.
- **Cache writes**: atomic via `tempfile.mkstemp()` + `os.replace()` with temp file cleanup on failure.
- **Data source fallbacks**: API `used_percentage` is primary; transcript token parsing is fallback. Discrepancies >10% shown in red curly braces when opted in via `percentage:fallback=1` / `tokens:fallback=1` (default off).
- **No type hints** per project convention — uses f-strings throughout.
