# Mac Disk Cleaner CLI

An interactive macOS disk space cleaner that runs entirely in your terminal. Zero dependencies — just Python 3.6+ and macOS.

## Install

```bash
pip install git+https://github.com/raghut/mac-disk-cleaner-cli.git
```

Then run it from anywhere:

```bash
disk-cleaner
disk-cleaner --dry-run
```

### Or run without installing

```bash
git clone https://github.com/raghut/mac-disk-cleaner-cli.git
cd mac-disk-cleaner-cli
python3 disk_cleaner.py
```

## What It Scans

| # | Category | Safe | What it finds |
|---|----------|------|---------------|
| 1 | Trash | Yes | `~/.Trash` contents |
| 2 | Dev caches | Yes | npm, Gradle, Maven, pip, Go, Homebrew, node-gyp, TypeScript |
| 3 | Xcode caches | Yes | DerivedData, Archives, iOS DeviceSupport, CoreSimulator |
| 4 | Android SDK (old) | Yes | Old build-tools, platforms, system-images, NDK versions |
| 5 | JetBrains / IDE | Yes | Old JetBrains caches, old Android Studio data |
| 6 | VS Code caches | Yes | Cache, CachedData, CachedExtensions, logs |
| 7 | Language toolchains | Yes | Cargo, Yarn, pnpm, Conda caches; old pyenv/rustup versions |
| 8 | System logs | Yes | `~/Library/Logs` subdirectories > 50 MB |
| 9 | Saved app state | Yes | `~/Library/Saved Application State` entries > 1 MB |
| 10 | App caches (>100 MB) | Review | Large entries in `~/Library/Caches` |
| 11 | Docker | Review | Unused images, containers, networks, build cache |
| 12 | iOS backups | Review | Device backups in `~/Library/Application Support/MobileSync/Backup` |
| 13 | Large home folders | Review | Items > 500 MB in Documents, Downloads, Desktop, Movies |
| 14 | Large personal files | Review | Large .mp4, .mov, .dmg, .iso, .zip files |
| 15 | Installed applications | Review | All apps in `/Applications` |

**Safe** = caches/derived data that will be regenerated automatically.
**Review** = may contain data you want to keep — inspect before deleting.

## Features

- **No dependencies** — uses only Python standard library modules
- **Dry-run mode** — preview what would be deleted with `--dry-run`
- **Clickable paths** — file paths are terminal hyperlinks (OSC 8); click to open in Finder
- **Reveal in Finder** — type `r3` to open item #3 in Finder before deciding
- **Range selection** — select items with `1,3-5,7` syntax
- **Pre-deletion summary** — review every item and its full path before confirming
- **Size-sorted** — items shown largest-first so you can prioritize
- **15 scan categories** — from dev caches to iOS backups

## Usage

```
$ disk-cleaner

🔍 Scanning your disk...

┌─────────────────────────────────────────────────────────────┐
│  DISK CLEANER                     Free: 23.6 GB / 228.3 GB  │
└─────────────────────────────────────────────────────────────┘

  CATEGORY                         FOUND          RECLAIMABLE
  ──────────────────────────────────────────────────────────────
  [1] Trash                        1 items        1.2 GB         ✅ auto-safe
  [2] Dev caches                   9 items        9.1 GB         ✅ auto-safe
  ...

  Select categories to clean (e.g. 1,2,3 or 'all' or 'q' to quit): 2
```

Within a category, you can:
- Select items: `1,2` or `1-5` or `all` or `none`
- Reveal in Finder: `r3` (opens item #3 in Finder)
- See full paths for every item before confirming deletion

## Requirements

- **macOS** (uses macOS-specific paths and `open` command)
- **Python 3.6+** (ships with macOS)
- No third-party dependencies

## License

MIT
