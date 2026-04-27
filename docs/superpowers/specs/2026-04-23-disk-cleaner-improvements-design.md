# Mac Disk Cleaner CLI — Improvements Design Spec

**Date:** 2026-04-23
**Status:** Approved
**Scope:** Three improvements to the existing disk cleaner CLI

## Overview

The mac-disk-cleaner-cli is a single-file Python CLI tool with 21 scan categories, interactive selection, and zero dependencies. This spec covers three improvements:

1. **Main menu loop** — return to menu after deletion instead of exiting
2. **New scan categories** — address the 10-20GB refill problem by covering missing cleanup targets
3. **Scheduled auto-clean** — optional launchd-based automation for safe categories

Architecture approach: **Incremental enhancement** of the existing single-file design (`disk_cleaner.py`), with one new file (`disk_cleaner_schedule.py`) for launchd scheduling logic.

---

## 1. Main Menu Loop

### Current Behavior
After processing selected categories, `main()` prints a summary and returns (line 1032), exiting the program. Users must re-run the tool to clean additional categories.

### New Behavior
- After processing selected categories, show the freed-space summary **inline** (not as an exit message)
- Prompt: `"Press 'r' to re-scan, 'q' to quit, or Enter to continue: "`
  - `r` — re-run `build_categories()`, refresh disk usage header, show updated main menu
  - `q` — show final session summary (total freed across all rounds) and exit
  - `Enter` — show main menu again with cached/adjusted sizes
- The **only** way to exit is `q` or Ctrl+C
- Track cumulative `total_freed` across all rounds, show in final exit summary
- After re-scan, refresh the disk usage header (free/total) so the user sees real progress

### Changes
- Remove the `return` at line 1032
- Replace with post-round prompt logic
- Move final summary to only trigger on explicit quit

---

## 2. New Scan Categories

### For Everyone (non-devs + devs)

| # | Category | Safe | What it finds |
|---|----------|------|---------------|
| 22 | Mail attachments | Review | `~/Library/Mail` downloads & attachments > 50MB |
| 23 | iCloud local cache | Yes | `~/Library/Caches/CloudKit`, `~/Library/Caches/com.apple.cloudd` |
| 24 | Diagnostic reports | Yes | `~/Library/Logs/DiagnosticReports`, `/Library/Logs/DiagnosticReports` |
| 25 | Core dumps | Yes | `/cores/` directory |
| 26 | Software update staging | Review | `/Library/Updates`, macOS installer staging files (sudo) |
| 27 | ASL logs | Yes | `/private/var/log/asl/` (sudo) |
| 28 | Spotlight index | Review | `.Spotlight-V100` — only offer rebuild, not delete |

### For Developers (auto-detected via directory existence)

| # | Category | Safe | What it finds |
|---|----------|------|---------------|
| 29 | Xcode simulator runtimes | Review | `~/Library/Developer/CoreSimulator/Caches` |
| 30 | CocoaPods cache | Yes | `~/Library/Caches/CocoaPods` |
| 31 | Composer cache (PHP) | Yes | `~/.composer/cache` |
| 32 | Ruby gems cache | Yes | `~/.gem` |
| 33 | NuGet cache (.NET) | Yes | `~/.nuget/packages` |

### Why These Categories

The 10-20GB refill problem is caused by macOS and apps continuously regenerating caches and logs:
- **ASL logs** — macOS writes them continuously, can grow to GBs
- **Diagnostic reports** — crash logs accumulate silently
- **Core dumps** — a single crash can leave a multi-GB core file
- **iCloud cache** — syncs and re-caches constantly
- **Browser caches** — Chrome alone regenerates 2-5GB within days

### Auto-Detect Logic
No explicit user profiling. Scanners return empty lists when tools aren't installed. Empty categories are hidden from the main menu (see Section 5).

---

## 3. Logging & Configuration

### Config Directory: `~/.disk-cleaner/`
- `config.json` — schedule preferences, user settings

### Log Directory: `~/Library/Logs/DiskCleaner/`
- `cleanup-YYYY-MM-DD.log` — one log file per day, viewable in Console.app
- Auto-rotate: delete log files older than 30 days on each run

### Config Format

```json
{
  "schedule": {
    "enabled": false,
    "frequency": "weekly",
    "day": "sunday",
    "time": "03:00",
    "categories": "safe-only"
  },
  "log_retention_days": 30
}
```

### Log Format

```
[2026-04-23 03:00:12] AUTO-CLEAN started
[2026-04-23 03:00:12] Deleted: npm cache — 1.2 GB — ~/.npm
[2026-04-23 03:00:13] Deleted: pip cache — 340 MB — ~/Library/Caches/pip
[2026-04-23 03:00:15] Skipped: Docker (requires review)
[2026-04-23 03:00:15] AUTO-CLEAN complete — freed 1.5 GB — disk free: 45.2 GB / 228.3 GB
```

### Changes to `disk_cleaner.py`
- Add `init_config()` — create `~/.disk-cleaner/` and default `config.json` on first run if not present
- Add `log_action(message)` — append to today's log file
- Wrap all delete functions to call `log_action()` after each deletion
- Add `cleanup_old_logs()` — called on startup, removes logs older than retention period

---

## 4. Scheduled Auto-Clean (launchd)

### How It Works
- `disk-cleaner --schedule` or interactive menu option `[s]` walks user through setup
- Generates a launchd plist installed to `~/Library/LaunchAgents/com.diskcleaner.auto.plist`
- Runs `disk-cleaner --auto-clean` on schedule — non-interactive mode that only cleans `safe=True` categories silently and logs everything
- No sudo required (user-level LaunchAgent)

### Interactive Setup Flow

```
  Auto-Clean Setup
  -----------------
  Frequency:  [1] Daily  [2] Weekly  [3] Monthly
  > 2

  Day:  [1] Monday ... [7] Sunday
  > 7

  Time (24h format, e.g. 03:00):
  > 03:00

  Categories to auto-clean:
    [ok] Trash
    [ok] Dev caches (npm, Gradle, pip, etc.)
    [ok] Xcode caches
    [ok] VS Code caches
    [ok] Browser caches
    [ok] Language toolchains
    [ok] System logs
    [ok] Saved app state
    [ok] Diagnostic reports
    [ok] Core dumps
    [ok] ASL logs
    [ok] iCloud local cache

  Include all safe categories? [Y/n]: y

  Schedule installed: every Sunday at 03:00
  Plist: ~/Library/LaunchAgents/com.diskcleaner.auto.plist
  Logs:  ~/Library/Logs/DiskCleaner/
```

### CLI Equivalents
- `disk-cleaner --schedule weekly --day sunday --time 03:00` — install schedule
- `disk-cleaner --unschedule` — remove launchd plist and disable
- `disk-cleaner --schedule-status` — show current schedule, last run, next run
- `disk-cleaner --auto-clean` — run non-interactive safe cleanup (called by launchd)

### Safety Guardrails
- `--auto-clean` mode **only** cleans categories marked `safe=True`
- Never touches "review" categories without interactive confirmation
- Logs every action — user can audit in Console.app
- If a deletion fails, logs the error and continues (doesn't abort entire run)
- Plist uses `StandardOutPath` and `StandardErrorPath` pointing to the log directory
- Categories requiring `sudo` are **skipped** in auto-clean mode (no password prompt possible)

### New File: `disk_cleaner_schedule.py`
- `generate_plist(config)` — create launchd XML plist
- `install_schedule(config)` — write plist to `~/Library/LaunchAgents/`, run `launchctl load`
- `uninstall_schedule()` — `launchctl unload`, remove plist
- `show_schedule_status()` — read plist, show next run time

---

## 5. Auto-Detect & Hide Empty Categories

### Current Behavior
All 21 categories always show in the main menu, even with 0 items found.

### New Behavior
- Categories with 0 items found are **hidden** from the main menu
- Summary line at bottom: `"(X categories hidden — nothing found)"`
- User can type `'a'` to show **all** categories including empty ones
- Category numbering is **dynamic** — renumbered based on visible items, no confusing gaps

### Example: Non-Developer User View

```
  CATEGORY                         FOUND          RECLAIMABLE
  ------------------------------------------------------------------
  [1] Trash                        1 items        1.2 GB         auto-safe
  [2] Browser caches               3 items        2.1 GB         auto-safe
  [3] App caches (>100 MB)         4 items        890 MB         review
  [4] Large home folders           2 items        3.5 GB         review
  [5] Mail attachments             6 items        1.8 GB         review
  [6] Diagnostic reports           12 items       450 MB         auto-safe

  (15 categories hidden — nothing found)
  Total reclaimable: ~9.9 GB
```

---

## 6. In-App Documentation

### Info Command
Add `[i]` info command to the main menu showing why disk fills up:

```
  Why does my disk fill up again?
  -------------------------------
  macOS and apps continuously regenerate caches, logs, and temp files.
  The biggest culprits:

  - Browser caches     — Chrome/Safari rebuild 2-5 GB within days
  - System logs (ASL)  — macOS writes continuously, can grow to GBs
  - Diagnostic reports — crash logs accumulate silently
  - iCloud sync cache  — re-downloads files as you access them
  - Spotlight index    — rebuilds after cache clears
  - Swap/VM files      — grow under memory pressure (freed on restart)

  To keep disk clean automatically, set up auto-clean:
  From main menu: press 's' to configure a schedule
  Or run: disk-cleaner --schedule weekly
```

### Per-Category Hints
Add a `hint` field to each category dict — one-line explanation shown when entering a category:

```
  Category: Browser caches  (2.1 GB reclaimable)
  Safe to delete — browsers rebuild their cache automatically.
  These typically refill within 1-2 days of normal browsing.
```

### Changes
- Add `hint` string field to each category dict
- Add optional `refill_info` field for categories that commonly refill
- Handle `'i'` input in the main menu loop
- Handle `'s'` input in the main menu loop (routes to schedule setup)

### Updated Main Menu Input
```
  Select categories (e.g. 1,2 / 'all' / 'a' show all / 's' schedule / 'i' info / 'q' quit):
```

---

## File Changes Summary

| File | Change |
|------|--------|
| `disk_cleaner.py` | Main menu loop, new scanners, logging, config init, hide empty categories, info/hints, schedule CLI args, auto-clean mode |
| `disk_cleaner_schedule.py` | New file — launchd plist generation, install/uninstall/status |
| `setup.py` | Add `disk_cleaner_schedule` to `py_modules` |
| `README.md` | Update with new categories, schedule docs, new menu options |

## Non-Goals
- No GUI or web interface
- No third-party dependencies
- No root/admin-level daemon (user-level LaunchAgent only)
- No cloud sync or telemetry
- No Windows/Linux support
