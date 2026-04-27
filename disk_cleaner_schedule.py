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
    result = subprocess.run(
        ["which", "disk-cleaner"], capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
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
    uninstall_schedule(quiet=True)

    plist = generate_plist(config)

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

    result = subprocess.run(
        ["launchctl", "list", PLIST_NAME],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  Status: Active (loaded)")
    else:
        print("  Status: Inactive (not loaded)")
