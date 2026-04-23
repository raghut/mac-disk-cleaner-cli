#!/usr/bin/env python3
"""
disk_cleaner.py — Interactive macOS disk space cleaner.
No third-party dependencies. Python 3.6+
Usage: python3 disk_cleaner.py [--dry-run]
"""

import os
import sys
import shutil
import subprocess
import pathlib
import argparse
import re
import json
import datetime
from typing import List, Tuple, Optional

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

HOME = pathlib.Path.home()
DRY_RUN = False
BACK_SENTINEL = "__BACK__"

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

# ─────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────

def get_size(path: pathlib.Path) -> int:
    """Recursively calculate directory/file size in bytes."""
    if not path.exists():
        return 0
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except (PermissionError, OSError):
            return 0
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink():
                    continue
                elif entry.is_dir(follow_symlinks=False):
                    total += get_size(pathlib.Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


def format_size(num_bytes: int) -> str:
    """Human-readable file size."""
    if num_bytes >= 1_073_741_824:
        return f"{num_bytes / 1_073_741_824:.1f} GB"
    elif num_bytes >= 1_048_576:
        return f"{num_bytes / 1_048_576:.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def hyperlink(path: pathlib.Path) -> str:
    """Wrap path in OSC 8 terminal hyperlink (clickable in Terminal.app/iTerm2/Warp)."""
    url = f"file://{path}"
    label = str(path).replace(str(HOME), "~", 1)
    return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"


def reveal_in_finder(path: pathlib.Path) -> None:
    """Open Finder at the given path."""
    if path.is_dir():
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["open", "-R", str(path)])


def dim(text: str) -> str:
    return f"\033[2m{text}\033[22m"


def bold(text: str) -> str:
    return f"\033[1m{text}\033[22m"


def parse_selection(raw: str, count: int) -> List[int]:
    """Parse '1,3-5,7' into zero-based indices, validated against count."""
    raw = raw.strip().lower()
    if raw == "all":
        return list(range(count))
    if raw in ("q", "quit", "exit", "none", ""):
        return []
    indices = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                indices.extend(range(int(a) - 1, int(b)))
            except ValueError:
                pass
        else:
            try:
                indices.append(int(part) - 1)
            except ValueError:
                pass
    return [i for i in indices if 0 <= i < count]


def confirm(msg: str) -> bool:
    """Prompt user for y/n confirmation."""
    while True:
        try:
            ans = input(f"{msg} [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False


def safe_delete(path: pathlib.Path) -> bool:
    """Delete a file or directory tree; returns True on success."""
    if DRY_RUN:
        print(f"  [dry-run] would delete: {path}")
        return True
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink()
        return True
    except Exception as e:
        print(f"  Error deleting {path}: {e}")
        return False


def print_header(free_bytes: int, total_bytes: int) -> None:
    free_str = format_size(free_bytes)
    total_str = format_size(total_bytes)
    width = 61
    title = "DISK CLEANER"
    right = f"Free: {free_str} / {total_str}"
    inner = f"  {title:<{width - len(right) - 4}}{right}  "
    print(f"\n\u250c{'─' * (width)}┐")
    print(f"│{inner}│")
    print(f"\u2514{'─' * (width)}┘\n")


def print_summary_table(categories: List[dict]) -> None:
    col_cat = 32
    col_found = 14
    col_size = 14
    col_flag = 0

    header = f"  {'CATEGORY':<{col_cat}} {'FOUND':<{col_found}} {'RECLAIMABLE':<{col_size}}"
    print(header)
    print("  " + "─" * 70)

    total = 0
    for i, cat in enumerate(categories, 1):
        name = cat["name"]
        items = cat["items"]
        size = cat["total_size"]
        safe = cat["safe"]
        flag = "\u2705 auto-safe" if safe else "\u26a0\ufe0f  review"
        found_str = f"{len(items)} items" if items is not None else "-"
        size_str = format_size(size) if size else "0 B"
        print(f"  [{i}] {name:<{col_cat - 4}} {found_str:<{col_found}} {size_str:<{col_size}} {flag}")
        total += size

    print()
    print(f"  Total reclaimable: ~{format_size(total)}")
    print()


def pick_items(items: List[Tuple[pathlib.Path, int, str]]) -> List[Tuple[pathlib.Path, int, str]]:
    """Show a list of items and let the user pick which ones to delete."""
    if not items:
        return []
    # Sort by size descending
    items = sorted(items, key=lambda x: x[1], reverse=True)
    for i, (path, size, label) in enumerate(items, 1):
        print(f"    [{i}] {label or path.name}  ({bold(format_size(size))})")
        print(f"         {dim(hyperlink(path))}")
    print()
    while True:
        try:
            raw = input("    Select items (e.g. 1,2 / 1-5 / 'all' / 'none' / 'b' back / 'r3' to reveal): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return []
        low = raw.lower()
        if low in ("b", "back"):
            return BACK_SENTINEL
        # Handle reveal command
        reveal_match = re.match(r'^r(?:eveal)?\s*(\d+)$', low)
        if reveal_match:
            idx = int(reveal_match.group(1)) - 1
            if 0 <= idx < len(items):
                reveal_in_finder(items[idx][0])
                print(f"    Revealed in Finder: {items[idx][0]}")
            else:
                print(f"    Invalid index: {reveal_match.group(1)}")
            continue
        selected_indices = parse_selection(low, len(items))
        if low in ("none", "", "q"):
            return []
        if selected_indices:
            return [items[i] for i in selected_indices]
        print("    Invalid input, try again.")


def run_cmd(cmd: List[str]) -> Optional[str]:
    """Run a subprocess command and return stdout, or None on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def spinner_print(msg: str) -> None:
    print(f"  \u23f3 {msg}", end="", flush=True)


def spinner_done() -> None:
    print(" done")


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
            date_str = entry.name[len("cleanup-"):-len(".log")]
            try:
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff:
                    entry.unlink()
            except ValueError:
                continue
    except OSError:
        pass


# ─────────────────────────────────────────────
# Scanner functions
# ─────────────────────────────────────────────

def scan_dev_caches() -> List[Tuple[pathlib.Path, int, str]]:
    paths = [
        (HOME / ".npm",                              "npm cache"),
        (HOME / ".gradle" / "caches",               "Gradle caches"),
        (HOME / ".gradle" / "wrapper",               "Gradle wrapper"),
        (HOME / ".m2",                               "Maven local repo"),
        (HOME / "Library/Caches/pip",                "pip cache"),
        (HOME / "Library/Caches/go-build",           "Go build cache"),
        (HOME / "Library/Caches/Homebrew",           "Homebrew cache"),
        (HOME / "Library/Caches/node-gyp",           "node-gyp cache"),
        (HOME / "Library/Caches/typescript",         "TypeScript cache"),
    ]
    results = []
    for path, label in paths:
        if path.exists():
            results.append((path, get_size(path), label))
    return results


def scan_xcode() -> List[Tuple[pathlib.Path, int, str]]:
    results = []
    derived = HOME / "Library/Developer/Xcode/DerivedData"
    if derived.exists():
        results.append((derived, get_size(derived), "Xcode DerivedData"))

    archives = HOME / "Library/Developer/Xcode/Archives"
    if archives.exists():
        results.append((archives, get_size(archives), "Xcode Archives"))

    ios_support = HOME / "Library/Developer/Xcode/iOS DeviceSupport"
    if ios_support.exists():
        results.append((ios_support, get_size(ios_support), "Xcode iOS DeviceSupport"))

    simulators = HOME / "Library/Developer/CoreSimulator/Devices"
    if simulators.exists():
        results.append((simulators, get_size(simulators), "CoreSimulator Devices"))

    return results


def scan_android_sdk() -> List[Tuple[pathlib.Path, int, str]]:
    sdk_candidates = [
        HOME / "Library/Android/sdk",
        pathlib.Path("/usr/local/share/android-sdk"),
        pathlib.Path("/opt/android-sdk"),
    ]
    sdk_root = next((p for p in sdk_candidates if p.exists()), None)
    if sdk_root is None:
        return []

    results = []
    for subdir_name in ("build-tools", "platforms", "system-images", "ndk"):
        subdir = sdk_root / subdir_name
        if not subdir.exists():
            continue
        try:
            versions = sorted([d for d in subdir.iterdir() if d.is_dir()])
        except (PermissionError, OSError):
            continue
        # Flag all but the newest version as "old"
        old_versions = versions[:-1] if len(versions) > 1 else []
        for v in old_versions:
            size = get_size(v)
            results.append((v, size, f"Android SDK {subdir_name}/{v.name} (old)"))

    return results


def _old_versions_only(entries: List[pathlib.Path]) -> List[pathlib.Path]:
    """Return all but the newest entry per product-name prefix."""
    groups: dict = {}
    for entry in entries:
        prefix = re.match(r'^[A-Za-z]+', entry.name)
        key = prefix.group(0) if prefix else entry.name
        groups.setdefault(key, []).append(entry)
    old = []
    for group in groups.values():
        group_sorted = sorted(group, key=lambda p: p.name)
        old.extend(group_sorted[:-1])
    return old


def scan_jetbrains() -> List[Tuple[pathlib.Path, int, str]]:
    results = []
    jb_caches = HOME / "Library/Caches/JetBrains"
    if jb_caches.exists():
        try:
            entries = [e for e in jb_caches.iterdir() if e.is_dir()]
            for entry in _old_versions_only(entries):
                results.append((entry, get_size(entry), f"JetBrains cache: {entry.name} (old)"))
        except (PermissionError, OSError):
            pass

    as_support = HOME / "Library/Application Support/Google"
    if as_support.exists():
        try:
            entries = [e for e in as_support.iterdir() if e.is_dir() and "AndroidStudio" in e.name]
            for entry in _old_versions_only(entries):
                results.append((entry, get_size(entry), f"Android Studio data: {entry.name} (old)"))
        except (PermissionError, OSError):
            pass

    return results


def scan_app_caches(min_mb: int = 100) -> List[Tuple[pathlib.Path, int, str]]:
    caches_dir = HOME / "Library/Caches"
    if not caches_dir.exists():
        return []
    results = []
    threshold = min_mb * 1_048_576
    try:
        for entry in caches_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"Cache: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_docker() -> List[Tuple[pathlib.Path, int, str]]:
    """Returns virtual items for Docker cleanup (paths are None placeholders)."""
    output = run_cmd(["docker", "system", "df"])
    if output is None:
        return []

    # Parse sizes from `docker system df` output
    items = []
    lines = output.strip().splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 4:
            category = parts[0]
            # SIZE is typically at index 3, RECLAIMABLE at 4
            try:
                size_str = parts[3]
                reclaim_str = parts[4] if len(parts) > 4 else "0B"
                size_bytes = _parse_docker_size(size_str)
                if size_bytes > 0:
                    # Use a sentinel path for docker items
                    items.append((pathlib.Path(f"__docker__{category}"), size_bytes, f"Docker {category}"))
            except (IndexError, ValueError):
                continue

    return items


def _parse_docker_size(s: str) -> int:
    """Parse Docker size strings like '1.2GB', '500MB', '0B'."""
    s = s.strip()
    try:
        for suffix, mult in [("GB", 1_073_741_824), ("MB", 1_048_576), ("KB", 1024), ("B", 1)]:
            if s.endswith(suffix):
                return int(float(s[:-len(suffix)]) * mult)
    except ValueError:
        pass
    return 0


def scan_large_home_folders(min_mb: int = 500) -> List[Tuple[pathlib.Path, int, str]]:
    scan_dirs = [
        HOME / "Documents",
        HOME / "Downloads",
        HOME / "Desktop",
        HOME / "Movies",
    ]
    threshold = min_mb * 1_048_576
    results = []
    for d in scan_dirs:
        if not d.exists():
            continue
        try:
            for entry in d.iterdir():
                if entry.is_symlink():
                    continue
                size = get_size(entry)
                if size >= threshold:
                    results.append((entry, size, f"{d.name}/{entry.name}"))
        except (PermissionError, OSError):
            continue
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_large_personal_files(min_mb: int = 200) -> List[Tuple[pathlib.Path, int, str]]:
    extensions = {".mp4", ".mov", ".mkv", ".avi", ".dmg", ".iso", ".zip"}
    threshold = min_mb * 1_048_576
    results = []
    scan_dirs = [
        HOME / "Documents",
        HOME / "Downloads",
        HOME / "Desktop",
        HOME / "Movies",
        HOME / "Pictures",
        HOME,
    ]
    seen = set()

    def _walk(d: pathlib.Path, depth: int = 0) -> None:
        if depth > 3:
            return
        try:
            for entry in d.iterdir():
                if entry.is_symlink() or str(entry) in seen:
                    continue
                seen.add(str(entry))
                if entry.is_file() and entry.suffix.lower() in extensions:
                    try:
                        size = entry.stat().st_size
                        if size >= threshold:
                            results.append((entry, size, f"{entry.name}  [{entry.parent}]"))
                    except (PermissionError, OSError):
                        pass
                elif entry.is_dir() and depth < 3:
                    # Don't recurse into Library or hidden system dirs
                    if entry.name not in ("Library", ".Trash", "node_modules", ".git"):
                        _walk(entry, depth + 1)
        except (PermissionError, OSError):
            pass

    for d in scan_dirs:
        if d.exists():
            _walk(d)

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_applications() -> List[Tuple[pathlib.Path, int, str]]:
    apps_dir = pathlib.Path("/Applications")
    results = []
    try:
        for entry in apps_dir.iterdir():
            if entry.suffix == ".app":
                size = get_size(entry)
                results.append((entry, size, entry.name))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_trash() -> List[Tuple[pathlib.Path, int, str]]:
    trash = HOME / ".Trash"
    if not trash.exists():
        return []
    size = get_size(trash)
    if size > 0:
        return [(trash, size, "Trash")]
    return []


def scan_system_logs() -> List[Tuple[pathlib.Path, int, str]]:
    logs_dir = HOME / "Library/Logs"
    if not logs_dir.exists():
        return []
    results = []
    threshold = 50 * 1_048_576
    try:
        for entry in logs_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"Logs: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_saved_app_state() -> List[Tuple[pathlib.Path, int, str]]:
    state_dir = HOME / "Library/Saved Application State"
    if not state_dir.exists():
        return []
    results = []
    threshold = 1 * 1_048_576
    try:
        for entry in state_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"Saved state: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_vscode() -> List[Tuple[pathlib.Path, int, str]]:
    base = HOME / "Library/Application Support/Code"
    subdirs = ["Cache", "CachedData", "CachedExtensions", "logs"]
    results = []
    for name in subdirs:
        path = base / name
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, f"VS Code {name}"))
    return results


def scan_language_toolchains() -> List[Tuple[pathlib.Path, int, str]]:
    results = []
    caches = [
        (HOME / ".cargo/registry",           "Cargo registry cache"),
        (HOME / "Library/Caches/Yarn",       "Yarn cache"),
        (HOME / ".yarn/cache",               "Yarn cache (v2+)"),
        (HOME / ".pnpm-store",               "pnpm store"),
        (HOME / ".conda/pkgs",               "Conda package cache"),
    ]
    for path, label in caches:
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, label))

    # Old versions of pyenv/rustup (keep newest)
    for base_path, label_prefix in [
        (HOME / ".pyenv/versions",    "Python version"),
        (HOME / ".rustup/toolchains", "Rust toolchain"),
    ]:
        if base_path.exists():
            try:
                entries = sorted([d for d in base_path.iterdir() if d.is_dir()])
            except (PermissionError, OSError):
                continue
            for old in _old_versions_only(entries):
                size = get_size(old)
                results.append((old, size, f"{label_prefix}: {old.name} (old)"))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_old_ios_backups() -> List[Tuple[pathlib.Path, int, str]]:
    backup_dir = HOME / "Library/Application Support/MobileSync/Backup"
    if not backup_dir.exists():
        return []
    results = []
    try:
        for entry in backup_dir.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                size = get_size(entry)
                results.append((entry, size, f"iOS backup: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_browser_caches() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan browser cache directories in ~/Library/Caches."""
    browsers = [
        (HOME / "Library/Caches/Google/Chrome",                  "Chrome cache"),
        (HOME / "Library/Caches/Google/Chrome/Default/Cache",    "Chrome default cache"),
        (HOME / "Library/Caches/com.apple.Safari",               "Safari cache"),
        (HOME / "Library/Caches/Firefox",                        "Firefox cache"),
        (HOME / "Library/Caches/com.microsoft.edgemac",          "Edge cache"),
    ]
    results = []
    for path, label in browsers:
        if path.exists():
            size = get_size(path)
            if size > 0:
                results.append((path, size, label))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_system_caches(min_mb: int = 100) -> List[Tuple[pathlib.Path, int, str]]:
    """Scan /Library/Caches for entries larger than min_mb."""
    caches_dir = pathlib.Path("/Library/Caches")
    if not caches_dir.exists():
        return []
    threshold = min_mb * 1_048_576
    results = []
    try:
        for entry in caches_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"System cache: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_tmp_files(min_mb: int = 50) -> List[Tuple[pathlib.Path, int, str]]:
    """Scan /tmp (/private/tmp) for entries larger than min_mb."""
    tmp_dir = pathlib.Path("/private/tmp")
    if not tmp_dir.exists():
        return []
    threshold = min_mb * 1_048_576
    results = []
    seen = set()
    try:
        for entry in tmp_dir.iterdir():
            if entry.is_symlink():
                continue
            resolved = entry.resolve()
            if str(resolved) in seen:
                continue
            seen.add(str(resolved))
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"Tmp: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_var_logs(min_mb: int = 50) -> List[Tuple[pathlib.Path, int, str]]:
    """Scan /private/var/log for entries larger than min_mb."""
    log_dir = pathlib.Path("/private/var/log")
    if not log_dir.exists():
        return []
    threshold = min_mb * 1_048_576
    results = []
    try:
        for entry in log_dir.iterdir():
            if entry.is_symlink():
                continue
            size = get_size(entry)
            if size >= threshold:
                results.append((entry, size, f"Var log: {entry.name}"))
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def scan_apfs_snapshots() -> List[Tuple[pathlib.Path, int, str]]:
    """List APFS local snapshots via tmutil."""
    output = run_cmd(["tmutil", "listlocalSnapshots", "/"])
    if not output:
        return []
    results = []
    for line in output.strip().splitlines():
        line = line.strip()
        # Lines look like "com.apple.TimeMachine.2024-01-15-123456.local"
        # or just the date portion depending on macOS version
        if not line:
            continue
        # Extract snapshot name (the date part)
        match = re.search(r'(\d{4}-\d{2}-\d{2}-\d+)', line)
        if match:
            snap_name = match.group(1)
            # Use a sentinel path with the snapshot name
            results.append((pathlib.Path(f"__snapshot__{snap_name}"), 0, f"APFS snapshot: {snap_name}"))
    return results


def scan_swap_sleep() -> List[Tuple[pathlib.Path, int, str]]:
    """Scan VM swap files and sleep image (info-only)."""
    vm_dir = pathlib.Path("/private/var/vm")
    if not vm_dir.exists():
        return []
    results = []
    try:
        for entry in vm_dir.iterdir():
            if entry.name.startswith("swapfile") or entry.name == "sleepimage":
                try:
                    size = entry.stat().st_size
                    if size > 0:
                        results.append((entry, size, f"VM: {entry.name}"))
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ─────────────────────────────────────────────
# Deletion functions
# ─────────────────────────────────────────────

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


def delete_docker(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Run docker system prune."""
    if DRY_RUN:
        print("  [dry-run] would run: docker system prune -af")
        total = sum(s for _, s, _ in selected)
        return total

    if not confirm("  Run 'docker system prune -af'? This removes all unused images, containers, networks, and build cache"):
        return 0

    result = run_cmd(["docker", "system", "prune", "-af"])
    if result is not None:
        print("  Docker pruned successfully.")
        log_action(f"Deleted: Docker prune — {format_size(sum(s for _, s, _ in selected))}")
        return sum(s for _, s, _ in selected)
    else:
        print("  Docker prune failed or docker not available.")
        log_action("Failed: Docker prune")
        return 0


def delete_trash(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Empty the Trash via Finder."""
    total = sum(s for _, s, _ in selected)
    if DRY_RUN:
        print("  [dry-run] would empty Trash")
        return total
    result = run_cmd(["osascript", "-e", 'tell application "Finder" to empty trash'])
    if result is not None:
        print("  Trash emptied successfully.")
        log_action(f"Deleted: Trash — {format_size(total)}")
        return total
    else:
        print("  Failed to empty Trash.")
        log_action("Failed: Trash empty")
        return 0


def delete_with_sudo(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Delete files/dirs using sudo. Returns total bytes freed."""
    freed = 0
    for path, size, label in selected:
        print(f"  Deleting {label} ({format_size(size)})... ", end="", flush=True)
        if DRY_RUN:
            print("[dry-run]")
            freed += size
            continue
        flag = "-rf" if path.is_dir() else "-f"
        result = subprocess.run(
            ["sudo", "rm", flag, str(path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            freed += size
            print("done")
            log_action(f"Deleted: {label} — {format_size(size)} — {path}")
        else:
            print(f"failed: {result.stderr.strip()}")
            log_action(f"Failed: {label} — {path} — {result.stderr.strip()}")
    return freed


def delete_apfs_snapshots(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Delete APFS local snapshots via tmutil. Returns total bytes freed."""
    freed = 0
    for path, size, label in selected:
        # The path name stores the snapshot date string
        snap_name = path.name
        print(f"  Deleting snapshot {snap_name} ({format_size(size)})... ", end="", flush=True)
        if DRY_RUN:
            print("[dry-run]")
            freed += size
            continue
        result = subprocess.run(
            ["sudo", "tmutil", "deletelocalsnapshots", snap_name],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            freed += size
            print("done")
        else:
            print(f"failed: {result.stderr.strip()}")
    return freed


def delete_info_only(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Info-only placeholder — these items are freed on restart."""
    return 0


def delete_applications(selected: List[Tuple[pathlib.Path, int, str]]) -> int:
    """Delete apps using osascript (Finder trash) to handle permissions."""
    freed = 0
    for path, size, label in selected:
        print(f"  Moving {label} to Trash ({format_size(size)})... ", end="", flush=True)
        if DRY_RUN:
            print(f"[dry-run]")
            freed += size
            continue
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        result = run_cmd(["osascript", "-e", script])
        if result is not None:
            freed += size
            print("done")
            log_action(f"Deleted: {label} — {format_size(size)} — {path}")
        else:
            # Fallback: try direct rm
            if safe_delete(path):
                freed += size
                print("done (direct)")
                log_action(f"Deleted: {label} — {format_size(size)} — {path}")
            else:
                print("failed")
                log_action(f"Failed: {label} — {path}")
    return freed


# ─────────────────────────────────────────────
# Category definitions
# ─────────────────────────────────────────────

def build_categories() -> List[dict]:
    """Run all scanners and return category list."""
    categories = []

    steps = [
        ("Trash",                    scan_trash,                True,  delete_trash),
        ("Dev caches",               scan_dev_caches,           True,  delete_paths),
        ("Xcode caches",             scan_xcode,                True,  delete_paths),
        ("Android SDK (old)",        scan_android_sdk,          True,  delete_paths),
        ("JetBrains / IDE",          scan_jetbrains,            True,  delete_paths),
        ("VS Code caches",           scan_vscode,               True,  delete_paths),
        ("Language toolchains",      scan_language_toolchains,  True,  delete_paths),
        ("System logs",              scan_system_logs,          True,  delete_paths),
        ("Saved app state",          scan_saved_app_state,      True,  delete_paths),
        ("App caches (>100 MB)",     scan_app_caches,           False, delete_paths),
        ("Docker",                   scan_docker,               False, delete_docker),
        ("iOS backups",              scan_old_ios_backups,      False, delete_paths),
        ("Large home folders",       scan_large_home_folders,   False, delete_paths),
        ("Large personal files",     scan_large_personal_files, False, delete_paths),
        ("Installed applications",   scan_applications,         False, delete_applications),
        ("Browser caches",           scan_browser_caches,       True,  delete_paths),
        ("System caches (>100 MB)",  scan_system_caches,        False, delete_with_sudo),
        ("Tmp files (>50 MB)",       scan_tmp_files,            False, delete_paths),
        ("Var logs (>50 MB)",        scan_var_logs,             False, delete_with_sudo),
        ("APFS snapshots",           scan_apfs_snapshots,       False, delete_apfs_snapshots),
        ("Swap / sleep image",       scan_swap_sleep,           False, delete_info_only),
    ]

    for name, scanner, safe, deleter in steps:
        spinner_print(f"Scanning {name}...")
        try:
            items = scanner()
        except Exception as e:
            items = []
        total = sum(s for _, s, _ in items)
        spinner_done()
        categories.append({
            "name": name,
            "items": items,
            "total_size": total,
            "safe": safe,
            "deleter": deleter,
        })

    return categories


# ─────────────────────────────────────────────
# Main flow
# ─────────────────────────────────────────────

def parse_category_selection(raw: str, count: int) -> List[int]:
    return parse_selection(raw, count)


def main() -> None:
    global DRY_RUN

    parser = argparse.ArgumentParser(
        description="Interactive macOS disk cleaner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without actually deleting anything")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    config = init_config()
    cleanup_old_logs(config.get("log_retention_days", 30))

    if DRY_RUN:
        print("\n  ** DRY-RUN MODE — nothing will be deleted **")

    print("\n\U0001f50d Scanning your disk...\n")

    usage = shutil.disk_usage(HOME)
    print_header(usage.free, usage.total)

    categories = build_categories()

    total_freed = 0

    while True:
        print()
        print_summary_table(categories)

        while True:
            try:
                raw = input("  Select categories to clean (e.g. 1,2,3 or 'all' or 'q' to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return

            if raw.lower() in ("q", "quit", "exit"):
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

            selected_indices = parse_category_selection(raw, len(categories))
            if not selected_indices:
                print("  No valid categories selected. Try again or 'q' to quit.\n")
                continue
            break

        went_back = False

        for idx in selected_indices:
            cat = categories[idx]
            print(f"\n{'─' * 65}")
            print(f"  Category: {cat['name']}  ({format_size(cat['total_size'])} reclaimable)")
            print(f"{'─' * 65}")

            items = cat["items"]
            if not items:
                print("  Nothing found in this category.")
                continue

            # Docker uses its own selection flow
            if cat["deleter"] is delete_docker:
                print(f"  Docker usage breakdown:")
                for path, size, label in items:
                    print(f"    • {label}: {format_size(size)}")
                print()
                freed = delete_docker(items)
                total_freed += freed
                if freed:
                    print(f"  Freed ~{format_size(freed)}")
                continue

            # Info-only categories (e.g. swap/sleep) — display and skip
            if cat["deleter"] is delete_info_only:
                for path, size, label in items:
                    print(f"    • {label}: {format_size(size)}")
                print()
                print("  These items are freed automatically on restart. No action taken.")
                continue

            selected_items = pick_items(items)
            if selected_items is BACK_SENTINEL:
                went_back = True
                break
            if not selected_items:
                print("  Nothing selected, skipping.")
                continue

            total_sel = sum(s for _, s, _ in selected_items)
            print(f"\n  Items to delete ({len(selected_items)} item(s), {bold(format_size(total_sel))}):")
            for path, size, label in selected_items:
                print(f"    • {label} ({bold(format_size(size))})")
                print(f"      {dim(hyperlink(path))}")
            print()
            if not confirm("  Proceed?"):
                print("  Skipped.")
                continue

            freed = cat["deleter"](selected_items)
            total_freed += freed
            print(f"  Freed {format_size(freed)}")

        if went_back:
            print("\n  Returning to main menu...\n")
            continue

        # Finished all selected categories without going back
        print(f"\n{'═' * 65}")
        if DRY_RUN:
            print(f"  [dry-run] Would have freed: {format_size(total_freed)}")
        else:
            print(f"  Total freed: {format_size(total_freed)}")
            new_usage = shutil.disk_usage(HOME)
            print(f"  Disk free now: {format_size(new_usage.free)} / {format_size(new_usage.total)}")
        print(f"{'═' * 65}\n")
        return


if __name__ == "__main__":
    main()
