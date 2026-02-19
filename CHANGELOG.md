# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
