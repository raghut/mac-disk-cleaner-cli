# Disk Cleaner Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add main menu loop, 12 new scan categories, logging/config, launchd scheduled auto-clean, hide-empty-categories UX, and in-app documentation to the disk cleaner CLI.

**Architecture:** Incremental enhancement of the existing single-file `disk_cleaner.py` plus one new file `disk_cleaner_schedule.py` for launchd plist management. Zero new dependencies.

**Tech Stack:** Python 3.6+ stdlib only (pathlib, json, datetime, plistlib, subprocess)

**Spec:** `docs/superpowers/specs/2026-04-23-disk-cleaner-improvements-design.md`

---

## File Structure

| File | Role | Change |
|------|------|--------|
| `disk_cleaner.py` | Main CLI — scanners, deleters, UI, config, logging | Modify |
| `disk_cleaner_schedule.py` | launchd plist generation, install/uninstall/status | Create |
| `setup.py` | Package config | Modify (add new module) |

---

### Task 1: Add Logging & Config Infrastructure

**Files:**
- Modify: `disk_cleaner.py` (add imports, constants, 4 new functions, wire into `main()`)

- [ ] **Step 1: Add new imports and constants**

Add after line 14 (`from typing import List, Tuple, Optional`):

```python
import json
import datetime
```

Add after line 23 (`BACK_SENTINEL = "__BACK__"`):

```python
CONFIG_DIR = HOME / ".disk-cleaner"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = HOME / "Library/Logs/DiskCleaner"

DEFAULT_CONFIG = {
    "schedule": {
        "enabled": False,
        "frequency": "weekly",
        "day": "sunday",
        "time": "03:00",
        "categories": "safe-only",
    },
    "log_retention_days": 30,
}
```

- [ ] **Step 2: Add config and logging functions**

Add after the `spinner_done()` function (after line 237), before the `# Scanner functions` section:

```python
# ─────────────────────────────────────────────
# Config & Logging
# ─────────────────────────────────────────────

def init_config() -> dict:
    """Create config dir and default config.json if not present. Returns config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        return dict(DEFAULT_CONFIG)
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """Write config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def log_action(message: str) -> None:
    """Append a timestamped line to today's log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    log_file = LOG_DIR / f"cleanup-{today}.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def cleanup_old_logs(retention_days: int = 30) -> None:
    """Delete log files older than retention_days."""
    if not LOG_DIR.exists():
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)
    try:
        for entry in LOG_DIR.iterdir():
            if not entry.name.startswith("cleanup-") or not entry.name.endswith(".log"):
                continue
            # Extract date from filename: cleanup-YYYY-MM-DD.log
            date_str = entry.name[len("cleanup-"):-len(".log")]
            try:
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff:
                    entry.unlink()
            except ValueError:
                continue
    except OSError:
        pass
```

- [ ] **Step 3: Wire config/logging into main()**

In the `main()` function, add after `DRY_RUN = args.dry_run` (line 920):

```python
    config = init_config()
    cleanup_old_logs(config.get("log_retention_days", 30))
```

- [ ] **Step 4: Add logging to delete_paths()**

Replace the `delete_paths` function (lines 730-740) with:

```python
def delete_paths(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Generic delete for file/dir items. Returns total bytes freed."""
    freed = 0
    for path, size, label in selected:
        print(f"  Deleting {label} ({format_size(size)})... ", end="", flush=True)
        if safe_delete(path):
            freed += size
            print("done")
            log_action(f"Deleted: {label} — {format_size(size)} — {path}")
        else:
            print("failed")
            log_action(f"Failed: {label} — {path}")
    return freed
```

- [ ] **Step 5: Add logging to delete_docker()**

In `delete_docker`, after `print("  Docker pruned successfully.")` (line 755), add:

```python
        log_action(f"Deleted: Docker prune — {format_size(sum(s for _, s, _ in selected))}")
```

After `print("  Docker prune failed or docker not available.")` (line 758), add:

```python
        log_action("Failed: Docker prune")
```

- [ ] **Step 6: Add logging to delete_trash()**

In `delete_trash`, after `print("  Trash emptied successfully.")` (line 770), add:

```python
        log_action(f"Deleted: Trash — {format_size(total)}")
```

After `print("  Failed to empty Trash.")` (line 773), add:

```python
        log_action("Failed: Trash empty")
```

- [ ] **Step 7: Add logging to delete_with_sudo()**

In `delete_with_sudo`, after `print("done")` (line 793), add:

```python
            log_action(f"Deleted: {label} — {format_size(size)} — {path}")
```

After the `print(f"failed: {result.stderr.strip()}")` (line 795), add:

```python
            log_action(f"Failed: {label} — {path} — {result.stderr.strip()}")
```

- [ ] **Step 8: Add logging to delete_applications()**

In `delete_applications`, after the first `print("done")` (line 840), add:

```python
            log_action(f"Deleted: {label} — {format_size(size)} — {path}")
```

After `print("done (direct)")` (line 845), add:

```python
                log_action(f"Deleted: {label} — {format_size(size)} — {path}")
```

After `print("failed")` (line 847), add:

```python
                log_action(f"Failed: {label} — {path}")
```

- [ ] **Step 9: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add logging and config infrastructure

- Config stored in ~/.disk-cleaner/config.json
- Logs written to ~/Library/Logs/DiskCleaner/cleanup-YYYY-MM-DD.log
- Auto-rotate logs older than 30 days
- All delete functions now log actions"
```

---

### Task 2: Add New Scanner Functions (Everyone Categories)

**Files:**
- Modify: `disk_cleaner.py` (add 7 new scanner functions after existing scanners)

- [ ] **Step 1: Add scan_mail_attachments()**

Add after `scan_swap_sleep()` function (after line 723):

```python
def scan_mail_attachments(min_mb: int = 50) -> List[Tuple[pathlib.Path, int, str]]:
    """Scan ~/Library/Mail for large attachments."""
    mail_dir = HOME / "Library/Mail"
    if not mail_dir.exists():
        return []
    threshold = min_mb * 1_048_576
    results = []
    seen = set()

    def _walk_mail(d: pathlib.Path, depth: int = 0) -> None:
        if depth > 6:
            return
        try:
            for entry in d.iterdir():
                if entry.is_symlink() or str(entry) in seen:
                    continue
                seen.add(str(entry))
                if entry.is_file():
                    try:
                        size = entry.stat().st_size
                        if size >= threshold:
                            results.append((entry, size, f"Mail: {entry.name}"))
                    except (PermissionError, OSError):
                        pass
                elif entry.is_dir():
                    _walk_mail(entry, depth + 1)
        except (PermissionError, OSError):
            pass

    _walk_mail(mail_dir)
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 2: Add scan_icloud_cache()**

```python
def scan_icloud_cache() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan iCloud-related caches."""
    paths = [
        (HOME / "Library/Caches/CloudKit",              "CloudKit cache"),
        (HOME / "Library/Caches/com.apple.cloudd",      "iCloud daemon cache"),
        (HOME / "Library/Caches/com.apple.bird",        "iCloud Documents cache"),
    ]
    results = []
    for path, label in paths:
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, label))
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 3: Add scan_diagnostic_reports()**

```python
def scan_diagnostic_reports() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan diagnostic/crash report directories."""
    dirs = [
        (HOME / "Library/Logs/DiagnosticReports",  "User diagnostic reports"),
        (pathlib.Path("/Library/Logs/DiagnosticReports"), "System diagnostic reports"),
    ]
    results = []
    for path, label in dirs:
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, label))
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 4: Add scan_core_dumps()**

```python
def scan_core_dumps() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan /cores/ for core dump files."""
    cores_dir = pathlib.Path("/cores")
    if not cores_dir.exists():
        return []
    results = []
    try:
        for entry in cores_dir.iterdir():
            if entry.is_file() and entry.name.startswith("core."):
                try:
                    size = entry.stat().st_size
                    if size > 0:
                        results.append((entry, size, f"Core dump: {entry.name}"))
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 5: Add scan_software_updates()**

```python
def scan_software_updates() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan macOS software update staging files."""
    dirs = [
        (pathlib.Path("/Library/Updates"),                           "macOS Updates staging"),
        (HOME / "Library/Caches/com.apple.SoftwareUpdate",          "SoftwareUpdate cache"),
    ]
    results = []
    for path, label in dirs:
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, label))
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 6: Add scan_asl_logs()**

```python
def scan_asl_logs() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan Apple System Logs at /private/var/log/asl/."""
    asl_dir = pathlib.Path("/private/var/log/asl")
    if not asl_dir.exists():
        return []
    size = get_size(asl_dir)
    if size > 0:
        return [(asl_dir, size, "Apple System Logs (ASL)")]
    return []
```

- [ ] **Step 7: Add scan_spotlight()**

```python
def scan_spotlight() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan Spotlight index size. Offers rebuild, not delete."""
    spotlight_dir = pathlib.Path("/.Spotlight-V100")
    if not spotlight_dir.exists():
        return []
    size = get_size(spotlight_dir)
    if size > 0:
        return [(pathlib.Path("__spotlight__"), size, "Spotlight index (rebuild to reclaim)")]
    return []
```

- [ ] **Step 8: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add 7 new scanner functions for everyone categories

- Mail attachments, iCloud cache, diagnostic reports, core dumps
- Software update staging, ASL logs, Spotlight index"
```

---

### Task 3: Add New Scanner Functions (Developer Categories)

**Files:**
- Modify: `disk_cleaner.py` (add 4 new scanner functions)

- [ ] **Step 1: Add scan_xcode_simulator_caches()**

Add after the previous new scanners:

```python
def scan_xcode_simulator_caches() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan Xcode simulator runtime caches."""
    cache_dir = HOME / "Library/Developer/CoreSimulator/Caches"
    if not cache_dir.exists():
        return []
    results = []
    try:
        for entry in cache_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size > 0:
                results.append((entry, size, f"Simulator cache: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results
```

- [ ] **Step 2: Add remaining dev cache scanners**

```python
def scan_cocoapods_cache() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan CocoaPods cache."""
    path = HOME / "Library/Caches/CocoaPods"
    if not path.exists():
        return []
    size = get_size(path)
    if size > 0:
        return [(path, size, "CocoaPods cache")]
    return []


def scan_composer_cache() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan PHP Composer cache."""
    path = HOME / ".composer/cache"
    if not path.exists():
        return []
    size = get_size(path)
    if size > 0:
        return [(path, size, "Composer cache")]
    return []


def scan_ruby_gems_cache() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan Ruby gems cache."""
    path = HOME / ".gem"
    if not path.exists():
        return []
    size = get_size(path)
    if size > 0:
        return [(path, size, "Ruby gems cache")]
    return []


def scan_nuget_cache() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan .NET NuGet package cache."""
    path = HOME / ".nuget/packages"
    if not path.exists():
        return []
    size = get_size(path)
    if size > 0:
        return [(path, size, "NuGet package cache")]
    return []
```

- [ ] **Step 3: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add 5 new scanner functions for developer categories

- Xcode simulator caches, CocoaPods, Composer, Ruby gems, NuGet"
```

---

### Task 4: Add New Deleter Functions

**Files:**
- Modify: `disk_cleaner.py` (add 2 new deleter functions)

- [ ] **Step 1: Add delete_spotlight_rebuild()**

Add after `delete_info_only()`:

```python
def delete_spotlight_rebuild(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Rebuild Spotlight index via mdutil instead of deleting files."""
    total = sum(s for _, s, _ in selected)
    if DRY_RUN:
        print("  [dry-run] would run: sudo mdutil -E /")
        return total
    if not confirm("  This will rebuild the Spotlight index (sudo mdutil -E /). Spotlight will be temporarily unavailable."):
        return 0
    result = subprocess.run(
        ["sudo", "mdutil", "-E", "/"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        print("  Spotlight index rebuild started.")
        log_action(f"Deleted: Spotlight index rebuild — {format_size(total)}")
        return total
    else:
        print(f"  Spotlight rebuild failed: {result.stderr.strip()}")
        log_action(f"Failed: Spotlight rebuild — {result.stderr.strip()}")
        return 0
```

- [ ] **Step 2: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add Spotlight rebuild deleter function"
```

---

### Task 5: Update build_categories() with Hints and New Categories

**Files:**
- Modify: `disk_cleaner.py` (rewrite `build_categories()`)

- [ ] **Step 1: Rewrite build_categories() with hint field and all new categories**

Replace the entire `build_categories()` function (lines 855-899) with:

```python
def build_categories() -> List[dict]:
    """Run all scanners and return category list."""
    categories = []

    # Format: (name, scanner, safe, deleter, hint)
    steps = [
        ("Trash",                    scan_trash,                   True,  delete_trash,
         "Safe to delete — empties your Trash bin."),
        ("Dev caches",               scan_dev_caches,              True,  delete_paths,
         "Safe to delete — package managers will re-download as needed."),
        ("Xcode caches",             scan_xcode,                   True,  delete_paths,
         "Safe to delete — Xcode rebuilds these on next build."),
        ("Android SDK (old)",        scan_android_sdk,             True,  delete_paths,
         "Safe to delete — old SDK versions no longer in use."),
        ("JetBrains / IDE",          scan_jetbrains,               True,  delete_paths,
         "Safe to delete — old IDE version caches."),
        ("VS Code caches",           scan_vscode,                  True,  delete_paths,
         "Safe to delete — VS Code rebuilds caches on restart."),
        ("Language toolchains",      scan_language_toolchains,     True,  delete_paths,
         "Safe to delete — package caches and old compiler versions."),
        ("System logs",              scan_system_logs,             True,  delete_paths,
         "Safe to delete — old log files no longer needed."),
        ("Saved app state",          scan_saved_app_state,         True,  delete_paths,
         "Safe to delete — app window state, regenerated on launch."),
        ("App caches (>100 MB)",     scan_app_caches,              False, delete_paths,
         "Review before deleting — app-specific caches, some may slow down apps temporarily."),
        ("Docker",                   scan_docker,                  False, delete_docker,
         "Review — removes unused images, containers, networks, and build cache."),
        ("iOS backups",              scan_old_ios_backups,         False, delete_paths,
         "Review carefully — device backups cannot be recovered once deleted."),
        ("Large home folders",       scan_large_home_folders,      False, delete_paths,
         "Review carefully — large items in Documents/Downloads/Desktop/Movies."),
        ("Large personal files",     scan_large_personal_files,    False, delete_paths,
         "Review carefully — large media files, disk images, and archives."),
        ("Installed applications",   scan_applications,            False, delete_applications,
         "Review — uninstall apps you no longer use."),
        ("Browser caches",           scan_browser_caches,          True,  delete_paths,
         "Safe to delete — browsers rebuild their cache automatically. Refills within 1-2 days."),
        ("System caches (>100 MB)",  scan_system_caches,           False, delete_with_sudo,
         "Review — system-level caches, requires sudo. Some may slow down apps temporarily."),
        ("Tmp files (>50 MB)",       scan_tmp_files,               False, delete_paths,
         "Review — temporary files that may still be in use by running processes."),
        ("Var logs (>50 MB)",        scan_var_logs,                False, delete_with_sudo,
         "Review — system log files, requires sudo."),
        ("APFS snapshots",           scan_apfs_snapshots,          False, delete_apfs_snapshots,
         "Review — Time Machine local snapshots. Deleting saves space but removes restore points."),
        ("Swap / sleep image",       scan_swap_sleep,              False, delete_info_only,
         "Info only — these are freed automatically on restart. Cannot be deleted while running."),
        # New categories
        ("Mail attachments",         scan_mail_attachments,        False, delete_paths,
         "Review — large email attachments. Deleting removes local copies only if using IMAP."),
        ("iCloud local cache",       scan_icloud_cache,            True,  delete_paths,
         "Safe to delete — iCloud re-downloads files as you access them. Refills over time."),
        ("Diagnostic reports",       scan_diagnostic_reports,      True,  delete_paths,
         "Safe to delete — crash logs and diagnostic data. Accumulates silently over time."),
        ("Core dumps",               scan_core_dumps,              True,  delete_with_sudo,
         "Safe to delete — process crash dumps, often multi-GB each."),
        ("Software updates",         scan_software_updates,        False, delete_with_sudo,
         "Review — macOS update staging files. Safe if no update is in progress."),
        ("ASL logs",                 scan_asl_logs,                True,  delete_with_sudo,
         "Safe to delete — Apple System Logs, continuously regenerated. Refills daily."),
        ("Spotlight index",          scan_spotlight,               False, delete_spotlight_rebuild,
         "Review — rebuilds search index. Spotlight unavailable temporarily during rebuild."),
        ("Xcode simulator caches",   scan_xcode_simulator_caches, False, delete_paths,
         "Review — simulator runtime caches. Re-downloaded when needed."),
        ("CocoaPods cache",          scan_cocoapods_cache,         True,  delete_paths,
         "Safe to delete — CocoaPods re-downloads pods on next install."),
        ("Composer cache (PHP)",     scan_composer_cache,          True,  delete_paths,
         "Safe to delete — Composer re-downloads packages on next install."),
        ("Ruby gems cache",          scan_ruby_gems_cache,         True,  delete_paths,
         "Safe to delete — gems re-downloaded on next bundle install."),
        ("NuGet cache (.NET)",       scan_nuget_cache,             True,  delete_paths,
         "Safe to delete — NuGet re-downloads packages on next restore."),
    ]

    for name, scanner, safe, deleter, hint in steps:
        spinner_print(f"Scanning {name}...")
        try:
            items = scanner()
        except Exception:
            items = []
        total = sum(s for _, s, _ in items)
        spinner_done()
        categories.append({
            "name": name,
            "items": items,
            "total_size": total,
            "safe": safe,
            "deleter": deleter,
            "hint": hint,
        })

    return categories
```

- [ ] **Step 2: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: wire 12 new categories into build_categories with hints

- All 33 categories now have hint text for in-app documentation
- New categories: Mail, iCloud, diagnostics, core dumps, software updates,
  ASL, Spotlight, Xcode sim caches, CocoaPods, Composer, Ruby, NuGet"
```

---

### Task 6: Hide Empty Categories & Dynamic Numbering

**Files:**
- Modify: `disk_cleaner.py` (rewrite `print_summary_table()`)

- [ ] **Step 1: Rewrite print_summary_table() to support filtering**

Replace the `print_summary_table` function (lines 157-181) with:

```python
def print_summary_table(categories: List[dict], show_all: bool = False) -> List[int]:
    """Print the category table. Returns mapping of display index to category index.
    If show_all is False, hides categories with 0 items."""
    col_cat = 32
    col_found = 14
    col_size = 14

    header = f"  {'CATEGORY':<{col_cat}} {'FOUND':<{col_found}} {'RECLAIMABLE':<{col_size}}"
    print(header)
    print("  " + "─" * 70)

    total = 0
    display_num = 0
    hidden_count = 0
    index_map = []  # display_index -> categories_index

    for cat_idx, cat in enumerate(categories):
        name = cat["name"]
        items = cat["items"]
        size = cat["total_size"]
        safe = cat["safe"]

        has_items = items is not None and len(items) > 0

        if not show_all and not has_items:
            hidden_count += 1
            continue

        display_num += 1
        index_map.append(cat_idx)
        flag = "\u2705 auto-safe" if safe else "\u26a0\ufe0f  review"
        found_str = f"{len(items)} items" if items is not None else "-"
        size_str = format_size(size) if size else "0 B"
        dimmed = "" if has_items else " (empty)"
        print(f"  [{display_num}] {name:<{col_cat - 4}} {found_str:<{col_found}} {size_str:<{col_size}} {flag}{dimmed}")
        total += size

    print()
    if hidden_count > 0:
        print(f"  ({hidden_count} categories hidden — nothing found)")
    print(f"  Total reclaimable: ~{format_size(total)}")
    print()

    return index_map
```

- [ ] **Step 2: Update main() to use index_map and handle 'a' input**

In `main()`, replace the section that calls `print_summary_table` and reads category selection (lines 934-962). The new code:

```python
    show_all = False

    while True:
        print()
        index_map = print_summary_table(categories, show_all=show_all)

        while True:
            try:
                raw = input("  Select categories (e.g. 1,2 / 'all' / 'a' show all / 's' schedule / 'i' info / 'q' quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return

            low = raw.lower()

            if low in ("q", "quit", "exit"):
                print("  Goodbye.")
                if total_freed:
                    print(f"\n{'═' * 65}")
                    if DRY_RUN:
                        print(f"  [dry-run] Would have freed: {format_size(total_freed)}")
                    else:
                        print(f"  Total freed: {format_size(total_freed)}")
                        new_usage = shutil.disk_usage(HOME)
                        print(f"  Disk free now: {format_size(new_usage.free)} / {format_size(new_usage.total)}")
                    print(f"{'═' * 65}\n")
                return

            if low == "a":
                show_all = not show_all
                break  # re-print the table

            if low == "i":
                print_info()
                continue

            if low == "s":
                interactive_schedule_setup(config)
                continue

            # Parse selection against visible categories
            if low == "all":
                selected_display = list(range(len(index_map)))
            else:
                selected_display = parse_selection(low, len(index_map))

            if not selected_display:
                print("  No valid categories selected. Try again or 'q' to quit.\n")
                continue

            # Map display indices back to actual category indices
            selected_indices = [index_map[d] for d in selected_display]
            break
        else:
            # 'a' was pressed — loop back to re-print
            continue
```

Note: The `else` clause on the inner `while` loop handles the case where `break` was NOT called (i.e., the `a` toggle). When `a` is pressed, the inner loop breaks, and we `continue` the outer loop to re-print.

Actually, a simpler approach — replace that section with:

```python
    show_all = False

    while True:
        print()
        index_map = print_summary_table(categories, show_all=show_all)

        selected_indices = None
        while selected_indices is None:
            try:
                raw = input("  Select categories (e.g. 1,2 / 'all' / 'a' show all / 's' schedule / 'i' info / 'q' quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return

            low = raw.lower()

            if low in ("q", "quit", "exit"):
                print("  Goodbye.")
                if total_freed:
                    print(f"\n{'═' * 65}")
                    if DRY_RUN:
                        print(f"  [dry-run] Would have freed: {format_size(total_freed)}")
                    else:
                        print(f"  Total freed: {format_size(total_freed)}")
                        new_usage = shutil.disk_usage(HOME)
                        print(f"  Disk free now: {format_size(new_usage.free)} / {format_size(new_usage.total)}")
                    print(f"{'═' * 65}\n")
                return

            if low == "a":
                show_all = not show_all
                # Re-print table with toggled visibility
                print()
                index_map = print_summary_table(categories, show_all=show_all)
                continue

            if low == "i":
                print_info()
                continue

            if low == "s":
                interactive_schedule_setup(config)
                continue

            # Parse selection against visible categories
            if low == "all":
                selected_display = list(range(len(index_map)))
            else:
                selected_display = parse_selection(low, len(index_map))

            if not selected_display:
                print("  No valid categories selected. Try again or 'q' to quit.\n")
                continue

            # Map display indices back to actual category indices
            selected_indices = [index_map[d] for d in selected_display]
```

- [ ] **Step 3: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: hide empty categories with dynamic numbering

- Categories with 0 items hidden by default
- 'a' toggles showing all categories
- Display numbers are sequential (no gaps)
- Shows count of hidden categories"
```

---

### Task 7: Main Menu Loop Fix

**Files:**
- Modify: `disk_cleaner.py` (replace exit-after-clean with post-round prompt)

- [ ] **Step 1: Replace the exit block after category processing**

Find the block at the end of the category processing loop (after `if went_back:` handling). Replace the final exit block (the lines starting with `# Finished all selected categories without going back` through `return`) with:

```python
        if went_back:
            print("\n  Returning to main menu...\n")
            continue

        # Show round summary inline
        round_freed = sum(
            cat["deleter"]  # Not needed — we already tracked total_freed above
        ) if False else 0  # placeholder — total_freed already accumulates

        print(f"\n{'─' * 65}")
        if DRY_RUN:
            print(f"  [dry-run] Session total so far: {format_size(total_freed)}")
        else:
            print(f"  Session total freed so far: {format_size(total_freed)}")
            new_usage = shutil.disk_usage(HOME)
            print(f"  Disk free now: {format_size(new_usage.free)} / {format_size(new_usage.total)}")
        print(f"{'─' * 65}")

        # Post-round prompt
        while True:
            try:
                post = input("\n  Press 'r' to re-scan, 'q' to quit, or Enter to continue: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return
            if post in ("q", "quit"):
                print("  Goodbye.")
                if total_freed:
                    print(f"\n{'═' * 65}")
                    if DRY_RUN:
                        print(f"  [dry-run] Would have freed: {format_size(total_freed)}")
                    else:
                        print(f"  Total freed: {format_size(total_freed)}")
                        final_usage = shutil.disk_usage(HOME)
                        print(f"  Disk free now: {format_size(final_usage.free)} / {format_size(final_usage.total)}")
                    print(f"{'═' * 65}\n")
                return
            if post == "r":
                print("\n\U0001f50d Re-scanning your disk...\n")
                usage = shutil.disk_usage(HOME)
                print_header(usage.free, usage.total)
                categories = build_categories()
                break
            if post == "":
                break
            print("  Invalid input. Press 'r', Enter, or 'q'.")
```

- [ ] **Step 2: Add hint display when entering a category**

In the category processing loop, after the line that prints the category header (`print(f"{'─' * 65}")`  after `Category: {cat['name']}`), add:

```python
            if cat.get("hint"):
                print(f"  {dim(cat['hint'])}")
```

- [ ] **Step 3: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: main menu loop — return to menu after deletion

- Post-round prompt: 'r' to re-scan, Enter to continue, 'q' to quit
- Re-scan refreshes disk usage header and all categories
- Session total freed tracked across all rounds
- Category hints shown when entering a category"
```

---

### Task 8: In-App Info Command

**Files:**
- Modify: `disk_cleaner.py` (add `print_info()` function)

- [ ] **Step 1: Add print_info() function**

Add before `main()`:

```python
def print_info() -> None:
    """Print info about why disk fills up and how to use auto-clean."""
    print(f"""
{'─' * 65}
  Why does my disk fill up again?
{'─' * 65}
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
{'─' * 65}
""")
```

- [ ] **Step 2: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add in-app info command explaining disk refill causes"
```

---

### Task 9: Auto-Clean Mode

**Files:**
- Modify: `disk_cleaner.py` (add `--auto-clean` arg and `run_auto_clean()` function)

- [ ] **Step 1: Add run_auto_clean() function**

Add before `main()`:

```python
def run_auto_clean() -> None:
    """Non-interactive mode: clean only safe categories, skip sudo, log everything."""
    global DRY_RUN

    config = init_config()
    cleanup_old_logs(config.get("log_retention_days", 30))

    log_action("AUTO-CLEAN started")
    print("Auto-clean: scanning...")

    # Build categories but skip printing spinners
    # Re-use build_categories — spinner output goes to stdout/log
    categories = build_categories()

    total_freed = 0
    for cat in categories:
        if not cat["safe"]:
            continue
        if not cat["items"]:
            continue
        # Skip categories that require sudo (can't prompt in auto mode)
        if cat["deleter"] in (delete_with_sudo, delete_spotlight_rebuild, delete_apfs_snapshots):
            log_action(f"Skipped: {cat['name']} (requires sudo)")
            continue

        freed = cat["deleter"](cat["items"])
        total_freed += freed
        if freed:
            log_action(f"Cleaned: {cat['name']} — freed {format_size(freed)}")

    usage = shutil.disk_usage(HOME)
    summary = f"AUTO-CLEAN complete — freed {format_size(total_freed)} — disk free: {format_size(usage.free)} / {format_size(usage.total)}"
    log_action(summary)
    print(f"  {summary}")
```

- [ ] **Step 2: Add --auto-clean argument and dispatch in main()**

In `main()`, add the argument after the `--dry-run` argument:

```python
    parser.add_argument("--auto-clean", action="store_true",
                        help="Run non-interactive cleanup of safe categories only (used by scheduler)")
```

After `DRY_RUN = args.dry_run`, add:

```python
    if args.auto_clean:
        run_auto_clean()
        return
```

- [ ] **Step 3: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add --auto-clean mode for non-interactive safe cleanup

- Only cleans safe=True categories
- Skips categories requiring sudo
- Logs all actions to ~/Library/Logs/DiskCleaner/"
```

---

### Task 10: Schedule Module (disk_cleaner_schedule.py)

**Files:**
- Create: `disk_cleaner_schedule.py`

- [ ] **Step 1: Create disk_cleaner_schedule.py**

```python
#!/usr/bin/env python3
"""
disk_cleaner_schedule.py — launchd plist management for disk-cleaner auto-clean.
No third-party dependencies. Python 3.6+
"""

import pathlib
import subprocess
import plistlib
import sys
from typing import Optional

HOME = pathlib.Path.home()
PLIST_NAME = "com.diskcleaner.auto"
PLIST_PATH = HOME / "Library/LaunchAgents" / f"{PLIST_NAME}.plist"
LOG_DIR = HOME / "Library/Logs/DiskCleaner"


def _find_disk_cleaner_path() -> str:
    """Find the installed disk-cleaner command path."""
    # Check if installed as a console_scripts entry point
    result = subprocess.run(
        ["which", "disk-cleaner"], capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    # Fallback: run via python module
    return f"{sys.executable} -m disk_cleaner"


def generate_plist(config: dict) -> dict:
    """Generate a launchd plist dict from schedule config."""
    schedule = config.get("schedule", {})
    frequency = schedule.get("frequency", "weekly")
    day = schedule.get("day", "sunday")
    time_str = schedule.get("time", "03:00")

    try:
        hour, minute = [int(x) for x in time_str.split(":")]
    except (ValueError, AttributeError):
        hour, minute = 3, 0

    day_map = {
        "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
        "thursday": 4, "friday": 5, "saturday": 6,
    }

    calendar_interval = {"Hour": hour, "Minute": minute}

    if frequency == "weekly":
        weekday = day_map.get(day.lower(), 0)
        calendar_interval["Weekday"] = weekday
    elif frequency == "monthly":
        calendar_interval["Day"] = 1
    # daily = just hour+minute, no extra keys

    cmd_path = _find_disk_cleaner_path()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": PLIST_NAME,
        "ProgramArguments": cmd_path.split() + ["--auto-clean"],
        "StartCalendarInterval": calendar_interval,
        "StandardOutPath": str(LOG_DIR / "launchd-stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd-stderr.log"),
        "RunAtLoad": False,
    }

    return plist


def install_schedule(config: dict) -> bool:
    """Write plist and load it via launchctl. Returns True on success."""
    # Unload first if already loaded
    uninstall_schedule(quiet=True)

    plist = generate_plist(config)

    # Ensure LaunchAgents dir exists
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist, f)
    except OSError as e:
        print(f"  Error writing plist: {e}")
        return False

    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  Error loading plist: {result.stderr.strip()}")
        return False

    return True


def uninstall_schedule(quiet: bool = False) -> bool:
    """Unload and remove the launchd plist. Returns True on success."""
    if not PLIST_PATH.exists():
        if not quiet:
            print("  No schedule found.")
        return True

    result = subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True, text=True,
    )

    try:
        PLIST_PATH.unlink()
    except OSError as e:
        if not quiet:
            print(f"  Error removing plist: {e}")
        return False

    if not quiet:
        print("  Schedule removed.")
    return True


def show_schedule_status() -> None:
    """Show current schedule status."""
    if not PLIST_PATH.exists():
        print("  No auto-clean schedule configured.")
        print("  Run 'disk-cleaner --schedule weekly' or press 's' in the main menu to set one up.")
        return

    try:
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException):
        print("  Schedule plist exists but could not be read.")
        return

    interval = plist.get("StartCalendarInterval", {})
    hour = interval.get("Hour", "?")
    minute = interval.get("Minute", "?")
    time_str = f"{hour:02d}:{minute:02d}" if isinstance(hour, int) else f"{hour}:{minute}"

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    if "Weekday" in interval:
        weekday = interval["Weekday"]
        day_name = day_names[weekday] if 0 <= weekday < 7 else f"day {weekday}"
        freq = f"Weekly on {day_name}"
    elif "Day" in interval:
        freq = f"Monthly on day {interval['Day']}"
    else:
        freq = "Daily"

    print(f"  Auto-clean schedule: {freq} at {time_str}")
    print(f"  Plist: {PLIST_PATH}")
    print(f"  Logs:  {LOG_DIR}")

    # Check if loaded
    result = subprocess.run(
        ["launchctl", "list", PLIST_NAME],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  Status: Active (loaded)")
    else:
        print("  Status: Inactive (not loaded)")
```

- [ ] **Step 2: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner_schedule; print('OK')"`
Expected: `OK`

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner_schedule.py
git commit -m "feat: add launchd schedule module

- generate_plist() creates launchd XML config
- install_schedule() writes plist and runs launchctl load
- uninstall_schedule() unloads and removes plist
- show_schedule_status() displays current schedule info"
```

---

### Task 11: Schedule CLI & Interactive Setup

**Files:**
- Modify: `disk_cleaner.py` (add CLI args, import schedule module, add interactive setup)

- [ ] **Step 1: Add schedule import at top of disk_cleaner.py**

After the existing imports (line 15), add:

```python
try:
    import disk_cleaner_schedule
except ImportError:
    disk_cleaner_schedule = None
```

- [ ] **Step 2: Add interactive_schedule_setup() function**

Add before `main()`:

```python
def interactive_schedule_setup(config: dict) -> None:
    """Interactive schedule configuration from the main menu."""
    if disk_cleaner_schedule is None:
        print("  Schedule module not found. Reinstall disk-cleaner to enable scheduling.")
        return

    print(f"\n{'─' * 65}")
    print("  Auto-Clean Setup")
    print(f"{'─' * 65}\n")

    # Frequency
    print("  Frequency:")
    print("    [1] Daily")
    print("    [2] Weekly")
    print("    [3] Monthly")
    while True:
        try:
            freq_input = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return
        if freq_input == "1":
            frequency = "daily"
            break
        elif freq_input == "2":
            frequency = "weekly"
            break
        elif freq_input == "3":
            frequency = "monthly"
            break
        print("  Please enter 1, 2, or 3.")

    # Day (only for weekly)
    day = "sunday"
    if frequency == "weekly":
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        print("\n  Day:")
        for i, d in enumerate(day_names, 1):
            print(f"    [{i}] {d.capitalize()}")
        while True:
            try:
                day_input = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Cancelled.")
                return
            try:
                day_idx = int(day_input) - 1
                if 0 <= day_idx < 7:
                    day = day_names[day_idx]
                    break
            except ValueError:
                pass
            print("  Please enter 1-7.")

    # Time
    print("\n  Time (24h format, e.g. 03:00):")
    while True:
        try:
            time_input = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return
        if len(time_input) >= 3 and ":" in time_input:
            try:
                h, m = [int(x) for x in time_input.split(":")]
                if 0 <= h <= 23 and 0 <= m <= 59:
                    time_str = f"{h:02d}:{m:02d}"
                    break
            except ValueError:
                pass
        print("  Please enter time in HH:MM format (e.g. 03:00).")

    # Show safe categories
    print("\n  Categories that will be auto-cleaned (safe only):")
    safe_names = [
        "Trash", "Dev caches", "Xcode caches", "Android SDK (old)",
        "JetBrains / IDE", "VS Code caches", "Language toolchains",
        "System logs", "Saved app state", "Browser caches",
        "iCloud local cache", "Diagnostic reports", "CocoaPods cache",
        "Composer cache (PHP)", "Ruby gems cache", "NuGet cache (.NET)",
    ]
    for name in safe_names:
        print(f"    [ok] {name}")

    print()
    if not confirm("  Include all safe categories?"):
        print("  Cancelled.")
        return

    # Save config
    config["schedule"] = {
        "enabled": True,
        "frequency": frequency,
        "day": day,
        "time": time_str,
        "categories": "safe-only",
    }
    save_config(config)

    # Install schedule
    if disk_cleaner_schedule.install_schedule(config):
        freq_display = frequency
        if frequency == "weekly":
            freq_display = f"every {day.capitalize()}"
        elif frequency == "monthly":
            freq_display = "monthly (1st)"

        print(f"\n  Schedule installed: {freq_display} at {time_str}")
        print(f"  Plist: ~/Library/LaunchAgents/com.diskcleaner.auto.plist")
        print(f"  Logs:  ~/Library/Logs/DiskCleaner/")
        log_action(f"Schedule installed: {freq_display} at {time_str}")
    else:
        print("\n  Failed to install schedule.")

    print()
```

- [ ] **Step 3: Add schedule CLI arguments to main()**

In `main()`, add after the `--auto-clean` argument:

```python
    parser.add_argument("--schedule", nargs="?", const="interactive", default=None,
                        metavar="FREQ",
                        help="Set up auto-clean schedule (daily/weekly/monthly or interactive)")
    parser.add_argument("--day", default="sunday",
                        help="Day for weekly schedule (default: sunday)")
    parser.add_argument("--time", default="03:00", dest="schedule_time",
                        help="Time for schedule in HH:MM format (default: 03:00)")
    parser.add_argument("--unschedule", action="store_true",
                        help="Remove auto-clean schedule")
    parser.add_argument("--schedule-status", action="store_true",
                        help="Show current auto-clean schedule status")
```

After the `auto_clean` dispatch (after the `if args.auto_clean:` block), add:

```python
    if args.schedule_status:
        if disk_cleaner_schedule:
            disk_cleaner_schedule.show_schedule_status()
        else:
            print("  Schedule module not available.")
        return

    if args.unschedule:
        if disk_cleaner_schedule:
            disk_cleaner_schedule.uninstall_schedule()
            log_action("Schedule removed")
        else:
            print("  Schedule module not available.")
        return

    if args.schedule is not None:
        config = init_config()
        if args.schedule == "interactive":
            interactive_schedule_setup(config)
            return
        # CLI schedule: --schedule weekly --day sunday --time 03:00
        config["schedule"] = {
            "enabled": True,
            "frequency": args.schedule,
            "day": args.day,
            "time": args.schedule_time,
            "categories": "safe-only",
        }
        save_config(config)
        if disk_cleaner_schedule and disk_cleaner_schedule.install_schedule(config):
            print(f"  Schedule installed: {args.schedule} at {args.schedule_time}")
            log_action(f"Schedule installed: {args.schedule} at {args.schedule_time}")
        else:
            print("  Failed to install schedule.")
        return
```

- [ ] **Step 4: Verify and commit**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -c "import disk_cleaner; print('OK')"`
Expected: `OK`

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 disk_cleaner.py --help`
Expected: Shows help with `--schedule`, `--unschedule`, `--schedule-status`, `--auto-clean` options.

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add disk_cleaner.py
git commit -m "feat: add schedule CLI args and interactive setup

- --schedule weekly/daily/monthly with --day and --time options
- --unschedule to remove launchd schedule
- --schedule-status to show current schedule
- 's' in main menu for interactive setup walkthrough"
```

---

### Task 12: Update setup.py

**Files:**
- Modify: `setup.py`

- [ ] **Step 1: Add disk_cleaner_schedule to py_modules**

Replace `py_modules=["disk_cleaner"],` with:

```python
    py_modules=["disk_cleaner", "disk_cleaner_schedule"],
```

- [ ] **Step 2: Bump version**

Replace `version="1.0.0",` with:

```python
    version="2.0.0",
```

- [ ] **Step 3: Commit**

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add setup.py
git commit -m "chore: add schedule module to setup.py, bump to v2.0.0"
```

---

### Task 13: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the "What It Scans" table**

Add these rows to the table after row 21:

```markdown
| 22 | Mail attachments | Review | Large attachments in `~/Library/Mail` |
| 23 | iCloud local cache | Yes | CloudKit, iCloud daemon caches |
| 24 | Diagnostic reports | Yes | Crash logs in `~/Library/Logs/DiagnosticReports` |
| 25 | Core dumps | Yes | Process crash dumps in `/cores/` |
| 26 | Software updates | Review | macOS update staging files (sudo) |
| 27 | ASL logs | Yes | Apple System Logs in `/private/var/log/asl/` (sudo) |
| 28 | Spotlight index | Review | Offers Spotlight index rebuild |
| 29 | Xcode simulator caches | Review | `~/Library/Developer/CoreSimulator/Caches` |
| 30 | CocoaPods cache | Yes | `~/Library/Caches/CocoaPods` |
| 31 | Composer cache (PHP) | Yes | `~/.composer/cache` |
| 32 | Ruby gems cache | Yes | `~/.gem` |
| 33 | NuGet cache (.NET) | Yes | `~/.nuget/packages` |
```

- [ ] **Step 2: Add Auto-Clean section after Features**

Add this section:

```markdown
## Auto-Clean Schedule

Set up automatic cleaning of safe categories via macOS launchd:

```bash
# Interactive setup
disk-cleaner --schedule

# CLI setup
disk-cleaner --schedule weekly --day sunday --time 03:00

# Check status
disk-cleaner --schedule-status

# Remove schedule
disk-cleaner --unschedule
```

Auto-clean only touches safe categories (caches that auto-regenerate). It never deletes items marked "Review" without your confirmation. All actions are logged to `~/Library/Logs/DiskCleaner/`.

You can also set up auto-clean from the main menu by pressing `s`.
```

- [ ] **Step 3: Update Features list**

Add these bullet points to the Features list:

```markdown
- **Auto-clean schedule** — set up launchd to clean safe categories on a schedule
- **Smart auto-detect** — only shows categories relevant to your setup (hides empty ones)
- **In-app help** — press `i` for info about why your disk fills up
- **Logging** — all cleanup actions logged to `~/Library/Logs/DiskCleaner/`
- **33 scan categories** — from dev caches to system-level temp files
```

Update the existing "21 scan categories" bullet to remove it (replaced by "33 scan categories" above).

- [ ] **Step 4: Update Usage example**

Update the main menu input line in the Usage section:

```
  Select categories to clean (e.g. 1,2,3 or 'all' or 'a' show all or 's' schedule or 'i' info or 'q' to quit): 2
```

- [ ] **Step 5: Commit**

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git add README.md
git commit -m "docs: update README with new categories, auto-clean, and features"
```

---

### Task 14: Final Integration Verification

- [ ] **Step 1: Syntax check**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 -m py_compile disk_cleaner.py && python3 -m py_compile disk_cleaner_schedule.py && echo "All OK"`
Expected: `All OK`

- [ ] **Step 2: Dry-run test**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 disk_cleaner.py --dry-run`
Expected: Shows scanning output, main menu with hidden empty categories, accepts input. Press `i` to see info. Press `q` to exit cleanly.

- [ ] **Step 3: Help output test**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 disk_cleaner.py --help`
Expected: Shows all arguments including `--auto-clean`, `--schedule`, `--unschedule`, `--schedule-status`.

- [ ] **Step 4: Schedule status test**

Run: `cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli && python3 disk_cleaner.py --schedule-status`
Expected: `No auto-clean schedule configured.`

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
cd /Users/raghu/Documents/code/personal/mac-disk-cleaner-cli
git log --oneline -10
```

Expected: Shows all commits from this implementation.
