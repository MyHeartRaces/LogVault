![LogVault wordmark](assets/WordMark.svg)

# LogVault

[Russian README](README.ru.md)

LogVault downloads World of Warcraft reports from the Warcraft Logs API v2 and saves them as local, readable export bundles. It is meant for sharing logs with another player, coach, or analysis tool without sending a pile of raw API responses.

## What It Exports

Each report bundle contains:

- `summary.md` - a human-readable overview of the selected fights.
- `fights.csv`, `actors.csv`, `abilities.csv` - report reference data.
- `tables/*.csv` and `tables/*.json` - aggregate Warcraft Logs tables such as damage, healing, casts, deaths, interrupts, buffs, debuffs, and resources.
- `events/*.jsonl` and `events/*.csv` - raw events, one event per JSONL line.
- A `.zip` archive next to the export folder for easy sharing.

Character batch exports also include:

- `index.md` - overview of all matched reports.
- `reports.csv` - report list with exported/skipped status.
- `manifest.json` - machine-readable batch manifest.

## Download Releases

Prebuilt single-file binaries are published on GitHub Releases:

- [Windows x64 executable](https://github.com/MyHeartRaces/LogVault/releases/latest)
- [Linux x64 binary](https://github.com/MyHeartRaces/LogVault/releases/latest)
- [macOS arm64 binary](https://github.com/MyHeartRaces/LogVault/releases/latest)

Windows SmartScreen may warn about the `.exe` because the binary is not code-signed.

## API Credentials

Warcraft Logs API v2 uses OAuth client credentials.

1. Create an API client in your Warcraft Logs profile/developer settings.
2. Copy `.env.example` to `.env`.
3. Fill in:

```bash
WCL_CLIENT_ID=...
WCL_CLIENT_SECRET=...
```

You do not need to fetch a token manually. LogVault automatically performs the equivalent OAuth request:

```bash
curl -u CLIENT_ID:CLIENT_SECRET -d grant_type=client_credentials https://www.warcraftlogs.com/oauth/token
```

Useful official links:

- [Warcraft Logs API docs](https://www.warcraftlogs.com/api/docs)
- [Warcraft Logs v2 API docs](https://www.warcraftlogs.com/v2-api-docs/warcraft/)

## Run From Source

Python 3.10+ is required.

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
logvault-gui
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
logvault-gui
```

You can also run without installing the package:

```bash
python3 run_gui.py
python3 run_cli.py REPORTCODE --fight last
```

On minimal Linux installs, Tkinter may be missing:

```bash
sudo apt install python3-tk
```

## GUI Usage

Launch:

```bash
logvault-gui
```

Single report mode downloads one Warcraft Logs report URL or report code. Character reports mode downloads recent reports for a character, filters them by season dates, then exports fights matching the selected difficulty.

Character fields:

- `Character` - character name.
- `Realm slug` - Warcraft Logs realm slug, for example `draenor` or `howling-fjord`.
- `Region` - `eu`, `us`, `kr`, `tw`, or `cn`.
- `Difficulty` - `All`, `Mythic`, `Heroic`, `Normal`, or `LFR`.
- `Season start` / `Season end` - `YYYY-MM-DD`.

## CLI Examples

Download one fight from a report URL:

```bash
logvault "https://www.warcraftlogs.com/reports/REPORTCODE#fight=12&type=damage-done"
```

Download the last boss pull:

```bash
logvault REPORTCODE --fight last
```

Download all boss pulls:

```bash
logvault REPORTCODE --fight boss
```

Download all fights, including trash:

```bash
logvault REPORTCODE --fight all
```

Fast export without raw events:

```bash
logvault REPORTCODE --events none
```

Download all available Mythic reports for a character in a season:

```bash
logvault \
  --character CharacterName \
  --server realm-slug \
  --region eu \
  --difficulty mythic \
  --season-start 2026-01-01 \
  --season-end 2026-06-30
```

Download every difficulty for the same season:

```bash
logvault --character CharacterName --server realm-slug --region eu --difficulty all --season-start 2026-01-01 --season-end 2026-06-30
```

## Arch Linux Desktop Entry

No AppImage is required. Download `LogVault-linux-x64`, `install_linux_desktop.sh`, and `logvault.svg` from the release, then run:

```bash
chmod +x LogVault-linux-x64 install_linux_desktop.sh
./install_linux_desktop.sh ./LogVault-linux-x64
```

This installs:

```text
~/.local/bin/LogVault
~/.local/share/applications/logvault.desktop
~/.local/share/icons/hicolor/scalable/apps/logvault.svg
```

LogVault should appear in GNOME, KDE, Xfce, and other desktop menus. If the menu does not update immediately, log out and back in.

Native Arch package:

```bash
cd packaging/arch
makepkg -si
```

## Build Single-File Binaries

PyInstaller builds for the current OS. Build Windows `.exe` on Windows, Linux binary on Linux, and macOS binary on macOS.

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Linux/macOS:

```bash
chmod +x scripts/build_unix.sh
./scripts/build_unix.sh
```

GitHub Actions also builds Windows, Linux, and macOS artifacts on tags:

```bash
git tag v0.3.0
git push origin v0.3.0
```

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

LogVault is open source under the [MIT License](LICENSE).
