# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
