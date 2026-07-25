# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [5.5.0] - 2026-07-25

### Added
- **`usage_fable` segment**: per-model weekly usage gauge, showing the separate
  weekly limit that `/usage` lists as its own row. Uses the same gauge styles,
  colors, and forward-looking ratio as `usage_5hour` / `usage_weekly`, and takes
  the same `gauge` and `width` options.
- `usage_fable:model=X` option to track any per-model limit (matched
  case-insensitively against the API's model display name). `Fable` is the
  default; the segment itself is generic.
- `usage_fable:only_current=1` option (default `0`) to show the gauge only while
  that model is the active one. In non-matching sessions it also skips the usage
  request entirely, so it costs nothing there.
- `usage_fable:label=` option (`full`/`short`/`none`, default `full`) labelling
  the gauge so it reads apart from the identically shaped 5h/7d gauges:
  `Fable`, `F`, or nothing. The text follows `model=`, so it stays correct
  when tracking a different model.

### Changed
- `usage_fable` is included in the **default** segment list. It is self-gating,
  so it stays invisible on accounts without a per-model weekly limit; remove it
  from `SL_SEGMENTS` (or set `only_current=1`) to avoid the usage request.

### Notes
- Whether an account has a per-model weekly limit depends on plan tier, model
  access, and API/extra-usage settings. The segment does not try to model those
  rules — it is self-gating, rendering only when the API actually returns a
  matching per-model limit and staying empty otherwise (the API exposes no
  plan/tier field, so the limit's presence is the only available check).
- Claude Code's stdin `rate_limits` carries only `five_hour` and `seven_day` —
  no per-model data at all, verified live through CC 2.1.220. The only
  available source is the deprecated OAuth API, so this segment triggers a
  usage fetch (disk-cached, ~1 request per 5 min) and it will stop rendering
  when that API is eventually removed. See "Limitations" in the README.

## [5.4.0] - 2026-06-11

### Added
- **Fable model badge color**: the `model` segment now renders a distinct badge
  for Fable models using Nord red (nord11 `#BF616A` on dark, muted `#A8505A` on
  light). Previously Fable fell back to the neutral default badge. Customizable
  via the new `model_fable` theme key.

## [5.3.0] - 2026-05-08

### Changed
- **Effort level detection** now reads the live value from stdin `effort.level`
  (CC 2.1.119+), the canonical source. Replaces the previous workaround that
  read from settings files. Effort badge now correctly reflects mid-session
  `/effort` changes (including `max`) and is omitted entirely on models without
  effort support.
- `model:effort=short` now renders `L/M/H/X/MAX` (was `L/M/H/A` plus first-letter
  fallback for unknown values). `xhigh` is `X`, `max` is `MAX`.
- `model:effort=full` now renders `low/medium/high/xhigh/max` (was
  `low/medium/high/auto`). `auto` no longer appears — Claude Code resolves it to
  a concrete level (auto means "use model default", not a runtime mode).

### Removed
- `CLAUDE_CODE_EFFORT_LEVEL` env var override (workaround no longer needed —
  stdin provides the live level).
- Settings-file fallback for effort detection (`.claude/settings.json` etc.).

## [5.2.1] - 2026-05-05

### Fixed
- Python 3.10 compatibility: replaced `datetime.UTC` (3.11+) with
  `datetime.timezone.utc` (available since 3.2). The script now runs on
  Python 3.10 (e.g. the default interpreter on Ubuntu 22.04 LTS). README
  updated to note the `tomli` fallback for custom themes on 3.10.

## [5.2.0] - 2026-03-31

### Added
- **Plugin system** for custom segments. Auto-discovers `.py` files in
  `.claude/statusline/` (project-level) and `~/.claude/statusline/` (global).
  Each plugin defines `register(api)` where `api` provides `add_segment()`,
  `fg()`, `bg()`, `text_color()`, `RESET`, `BOLD`. Registered segments become
  valid in `SL_SEGMENTS`. Plugin errors are silently ignored. The `ctx` dict
  passed to renderers includes `data` (raw JSON from Claude Code stdin) so
  plugins can access `session_id`, `cwd`, and other fields.

## [5.1.0] - 2026-03-21

### Added
- **Effort level display** in model badge via `model:effort=short` (L/M/H/A) or
  `model:effort=full` (low/medium/high/auto). Reads from settings files with
  precedence: env var → project-local → project → user global. Note: `max` level
  is session-only and cannot be detected.
- **Dump mode** (`SL_DUMP=1`) for development: appends every stdin JSON input with
  timestamp to `/tmp/claude-statusline-dump.jsonl`. Normal rendering continues.
- **Native rate_limits support**: reads usage data directly from CC 2.1.80+ stdin
  JSON (`rate_limits` field), eliminating the need for OAuth API calls. Falls back
  to deprecated OAuth API for older CC versions.

## [5.0.0] - 2026-03-06

### Removed
- Reasoning effort level display from model segment (`model:effort` option).
  Claude Code now shows effort level natively. Users with `model:effort=short`
  or `model:effort=full` in `SL_SEGMENTS` should remove the option.

## [4.13.1] - 2026-03-06

### Fixed
- Burndown noise suppression after weekly window reset — the relevance filter
  now scales inversely with the Bayesian trust factor, preventing misleading
  "may run out X sooner" warnings from stale or spiked utilization data in the
  first hours of a new window

## [4.13.0] - 2026-03-05

### Added
- New `worktree` segment displaying worktree info in `{curly braces}` when running
  in a `--worktree` session. Only renders when worktree data is present in JSON input.
  Supports `show` option: `name` (default), `branch`, `path`, `origin`, or
  comma-separated combo (e.g., `worktree:show=name,branch`). Path and origin apply
  `~` home shortening. New theme color `text_worktree` (Nord15 purple).

## [4.12.0] - 2026-03-04

### Removed
- Legacy context window fallback code: transcript parsing, `context_na_message`
  segment, `build_na_line()`, and `fallback` option for `percentage`/`tokens`
  segments. Claude Code now provides `used_percentage` reliably, making these
  mechanisms unnecessary. If `used_percentage` is missing, the status line produces
  no output instead of showing an N/A fallback.

## [4.11.0] - 2026-03-03

### Added
- Reasoning effort level display in model badge via `model:effort` option — shows
  `full` word (default), `short` single letter (H/M/L), or hidden. Reads from
  `CLAUDE_CODE_EFFORT_LEVEL` env var or `~/.claude/settings.json` `effortLevel` key.

## [4.10.0] - 2026-02-19

### Added
- New `added_dirs` segment showing directories added via `/add-dir` command, sorted
  alphabetically with muted gray styling. Supports `basename_only` and `separator`
  options (default separator: ` • `). Included in default segments after `directory`.

## [4.9.0] - 2026-02-17

### Added
- Bayesian burn rate shrinkage for burndown prognosis — blends observed burn rate
  toward on-track rate using a hyperbolic trust curve, dampening misleading warnings
  early in the weekly window (e.g. "may run out 1.9 d sooner" at 2% usage, 2.5h in)
- New `halftrust` option for `usage_burndown` segment (`usage_burndown:halftrust=16`)
  to configure the half-trust point in hours (default 16h)

## [4.8.0] - 2026-02-15

### Added
- New `basename_only` option for `directory` segment (`directory:basename_only=1`) —
  shows only the directory name instead of the full path, useful for deeply nested paths

## [4.7.0] - 2026-02-10

### Added
- Non-linear relevance filter for burndown predictions — suppresses noisy warnings
  early in the weekly window when prediction confidence is low
- New `coeff` option for `usage_burndown` segment (`usage_burndown:coeff=1.4`) to
  tune the power curve exponent controlling minimum "sooner" gap

## [4.6.0] - 2026-02-09

### Changed
- Burndown display now adapts to position in weekly window with three modes:
  Soon (< 1 h left), Pace (≥ 48 h left), Countdown (< 48 h left)
- Durations rounded for stability (e.g. `3 d`, `8 h` instead of `2 days 4 hours`)
- New `verbosity` option: `usage_burndown:verbosity=short` for compact output
  (`out ~ 3d sooner`, `~ 8h left -> 1d to renew`, compound durations like `5d2h30m`)

## [4.5.0] - 2026-02-06

### Changed
- Fallback display for `percentage` and `tokens` segments now defaults to off (was on)
- Users who want transcript-vs-API comparison in red curly braces must opt in via `percentage:fallback=1` / `tokens:fallback=1`

## [4.4.0] - 2026-02-05

### Added
- `git_status` segment showing working directory state with starship-inspired symbols:
  `+` staged, `!` modified, `x` deleted, `r` renamed, `?` untracked, `=` conflicted, `$` stashed, `>` ahead, `<` behind, `<>` diverged

## [4.3.0] - 2026-02-03

### Added
- `SL_UPDATE_CUSTOM_RETRY_DURATION` env var for faster retry after custom version command failures (2 min default vs 10 min for total failures)

### Improved
- Custom version command now retries 3 times with 1s delay before falling back to npm
- Better resilience for transient failures (e.g., cold nix cache, network hiccups)

## [4.2.0] - 2026-02-03

### Added
- `usage_burndown` segment showing how much sooner weekly budget will deplete vs reset time
- Displays "will run out X days Y hours sooner" when burning faster than sustainable (ratio < 1.0)
- Color-coded: orange in yellow zone (ratio ≥ 0.75), red in red zone (ratio < 0.75)

## [4.1.0] - 2026-01-31

### Added
- `SL_UPDATE_VERSION_CMD` env var to use a custom command for checking latest version (e.g., for Nix users)
- `SL_UPDATE_VERSION_SOURCE` env var to customize the source label in update notifications
- Cache auto-invalidates when version command changes

## [4.0.0] - 2026-01-30

### Breaking
- Users with custom `SL_SEGMENTS` must add `context_na_message` segment to see N/A fallback text when session data is unavailable

### Added
- `new_line` segment for multi-line statusline layouts
- `context_na_message` segment for explicit N/A message control

### Changed
- N/A message handling refactored to use segment system
- Segments joined with newline-aware logic (flush left after each newline)

## [3.3.0] - 2026-01-29

### Added
- `--self-update` flag to download and install latest version from GitHub
- Status line update notifications appear on separate line below main output
- `SL_SHOW_STATUSLINE_UPDATE` env var to control update notifications

## [3.2.0] - 2026-01-29

### Added
- Self-update checker for status line script (checks GitHub releases)
- `SL_STATUSLINE_CACHE_DURATION` env var for update check interval

## [3.1.0] - 2026-01-29

### Added
- Update checker (checks for new Claude Code releases on startup)

## [3.0.0] - 2026-01-28

### Security
- Hide OAuth token from process list
- Validate OAuth token characters before HTTP use
- Replace unsafe exec() theme loading with TOML parsing
- Atomic cache writes to prevent corruption

### Fixed
- Crash on non-numeric environment variable input
- ANSI escape sequences in git branch output
- Division by near-zero in usage ratio
- Naive datetimes default to UTC
- Progress bar width validation

### Added
- --demo-principle visualization
- --demo-gauge animation
- Cap gauge/progress bar widths at 128 chars
- Validate hex color string length

### Changed
- Reduce git branch subprocess timeout (1s to 0.3s)
- Simplified fallback comparison logic

## [2.0.0] - 2026-01-28

### Breaking
- Replaced 13 individual SL_* env vars with unified SL_SEGMENTS

### Added
- Segment reordering capability
- Per-segment inline options (width, style, fallback, etc.)

## [1.1.0] - 2026-01-27

### Added
- External theme file support (~/.claude/claude-code-theme.toml)
- Hex-only colors with auto-computed 256-color fallbacks
- Partial theme overrides inherit from base
- SL_THEME_FILE env var for custom theme path

## [1.0.0] - 2026-01-26

### Added
- Context window progress bar with sub-character precision
- Model badge (Opus/Sonnet/Haiku) with color coding
- Token count and percentage display
- Working directory and git branch indicator
- Usage/budget gauge (5-hour and 7-day limits)
- Dark and light themes (Nord-inspired)
- Custom theme support
- Truecolor (24-bit) with 256-color fallback
- All settings via SL_* environment variables
