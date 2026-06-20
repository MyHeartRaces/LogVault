![Логотип LogVault](assets/WordMark.svg)

# LogVault

[English README](README.md)

LogVault скачивает отчеты World of Warcraft через Warcraft Logs API v2 и сохраняет их в локальный, понятный пакет. Такой пакет удобно отправить другому игроку, рейд-лидеру, аналитику или загрузить в инструмент разбора.

## Что сохраняется

В обычном экспорте отчета будут:

- `summary.md` - короткий обзор выбранных боев.
- `fights.csv`, `actors.csv`, `abilities.csv` - справочники отчета.
- `tables/*.csv` и `tables/*.json` - агрегированные таблицы Warcraft Logs: урон, лечение, касты, смерти, прерывания, баффы, дебаффы, ресурсы.
- `events/*.jsonl.gz` и `events/*.csv` - опциональные сырые события. По умолчанию отключены, чтобы пакет не раздувался. Raw JSONL сжимается gzip, если экспорт событий включен.
- `.zip` для отправки и хранения. GUI по умолчанию оставляет только архив, чтобы рядом не лежала огромная распакованная папка.

При массовой выгрузке персонажа дополнительно создаются:

- `index.md` - обзор всех найденных отчетов.
- `reports.csv` - список отчетов со статусом exported/skipped.
- `manifest.json` - машинно-читаемый манифест выгрузки.

## Готовые сборки

Бинарники, установщики и пакеты публикуются в GitHub Releases:

- Windows: установщик `LogVault-Setup-*-x64.exe` и `LogVault-windows-x64-portable.exe`.
- Linux: Arch-пакет `logvault-bin-*-x86_64.pkg.tar.zst` и `LogVault-linux-x64-portable`.
- macOS: `LogVault-macos-arm64.dmg`.

Windows SmartScreen может ругаться на `.exe`, потому что бинарник не подписан платным code-signing сертификатом.

## Ключи Warcraft Logs

Warcraft Logs API v2 использует OAuth client credentials.

1. Создай API client в профиле Warcraft Logs.
2. Скопируй `.env.example` в `.env`.
3. Заполни:

```bash
WCL_CLIENT_ID=...
WCL_CLIENT_SECRET=...
```

Токен вручную получать не нужно. LogVault сам делает OAuth-запрос, эквивалентный:

```bash
curl -u CLIENT_ID:CLIENT_SECRET -d grant_type=client_credentials https://www.warcraftlogs.com/oauth/token
```

В GUI опция `Save credentials to app .env` сохраняет ключи в config-директорию приложения, если запущена установленная сборка. При запуске из исходников используется `.env` в репозитории.

Официальные ссылки:

- [Warcraft Logs API docs](https://www.warcraftlogs.com/api/docs)
- [Warcraft Logs v2 API docs](https://www.warcraftlogs.com/v2-api-docs/warcraft/)

## Запуск из исходников

Нужен Python 3.10+.

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

Можно запускать без установки пакета:

```bash
python3 run_gui.py
python3 run_cli.py REPORTCODE --fight last
```

На минимальных Linux-сборках может отсутствовать Tkinter:

```bash
sudo apt install python3-tk
```

## GUI

Запуск:

```bash
logvault-gui
```

`Single report` скачивает один отчет по URL или report code.

`Character reports` скачивает recent reports персонажа, сначала сканирует их, затем выгружает только завершенные бои выбранного game mode, zone/tier, difficulty scope и, если указано, только один encounter.

Режим событий по умолчанию - `compact`: сохраняются таблицы и summary, но не сырые event streams. `essential` выгружает небольшой набор событий: deaths, interrupts, dispels, combatant info. `full` включает все сырые события и все еще может быть большим, но raw JSONL хранится как `.jsonl.gz`, а главным файлом для отправки становится `.zip`.

В GUI включена опция `Keep only archive`: после экспорта остается только сжатый архив. Отключай ее только если нужна распакованная папка рядом с архивом. Во время активной выгрузки кнопка `Cancel` останавливает процесс после текущего API-запроса или ближайшей retry-паузы.

Запросы к Warcraft Logs автоматически повторяются при временных сетевых ошибках: dropped connection, incomplete read, HTTP 429 и HTTP 5xx. Если один отчет в массовой выгрузке все равно не скачался после всех попыток, он попадет в skipped, а выгрузка продолжит следующий отчет.

Массовая выгрузка поддерживает resume. LogVault после scan пишет стабильную batch-папку и `manifest.json`, затем скачивает по одному report. Повторный запуск с теми же фильтрами пропускает report-папки, где уже есть готовые `metadata.json` и `summary.md`.

Поля режима персонажа:

- `Character` - имя персонажа.
- `Realm slug` - slug реалма в Warcraft Logs, например `draenor` или `howling-fjord`.
- `Region` - `eu`, `us`, `kr`, `tw`, `cn`.
- `Game mode` - `All`, `Raids`, `Mythic+`, `Custom zone/tier`.
- `Zone/Tier` - необязательное имя зоны, raid tier или zone ID. Например `Sporefall`.
- `Difficulty` - `All`, `Mythic`, `Heroic`, `Mythic + Heroic`, `Normal`, `LFR`; можно также ввести scope через запятую или плюс.
- `Encounter` - необязательный encounter ID или имя босса, например `Fyrakk` или `2824`.
- `Completed only` - включено по умолчанию; незавершенные Mythic+ попытки и неубитые boss pulls не попадают в scan count и export.
- `Essential mode` - preset для character batch. Из Mythic+ остаются только timed runs на самом высоком закрытом в тайм уровне и уровне ниже для каждого dungeon. Из рейдов остаются завершенные Mythic boss fights. Preset использует собственный fight selection и принудительно включает completed-only поведение.
- `Season start` / `Season end` - даты в формате `YYYY-MM-DD`.

## CLI

Скачать конкретный бой из URL:

```bash
logvault "https://www.warcraftlogs.com/reports/REPORTCODE#fight=12&type=damage-done"
```

Скачать последний босс-пулл:

```bash
logvault REPORTCODE --fight last
```

Скачать все босс-пуллы:

```bash
logvault REPORTCODE --fight boss
```

Скачать только один энкаунтер из отчета:

```bash
logvault REPORTCODE --fight boss --encounter "Boss Name"
```

Скачать все файты, включая треш:

```bash
logvault REPORTCODE --fight all
```

Быстрый экспорт без сырых событий:

```bash
logvault REPORTCODE --events none
```

Выгрузить небольшой набор событий:

```bash
logvault REPORTCODE --events essential
```

Выгрузить все сырые события:

```bash
logvault REPORTCODE --events full
```

Оставить только сжатый bundle и удалить распакованную папку:

```bash
logvault REPORTCODE --archive-only
```

Скачать все доступные Mythic-отчеты персонажа за сезон:

```bash
logvault \
  --character CharacterName \
  --server realm-slug \
  --region eu \
  --difficulty mythic \
  --season-start 2026-01-01 \
  --season-end 2026-06-30
```

Скачать только Mythic и Heroic пуллы одного энкаунтера:

```bash
logvault \
  --character CharacterName \
  --server realm-slug \
  --region eu \
  --difficulty "mythic+heroic" \
  --encounter "Boss Name" \
  --season-start 2026-01-01 \
  --season-end 2026-06-30
```

Скачать завершенные Mythic+ отчеты:

```bash
logvault --character CharacterName --server realm-slug --region eu --content "mythic+" --season-start 2026-01-01 --season-end 2026-06-30
```

Скачать essential выборку сезона для разбора:

```bash
logvault --character CharacterName --server realm-slug --region eu --essential-mode --season-start 2026-01-01 --season-end 2026-06-30
```

Скачать custom raid tier, например Sporefall:

```bash
logvault --character CharacterName --server realm-slug --region eu --content "custom zone/tier" --zone Sporefall
```

Скачать все сложности за сезон:

```bash
logvault --character CharacterName --server realm-slug --region eu --difficulty all --season-start 2026-01-01 --season-end 2026-06-30
```

## Установщики и запуск из меню

Windows:

1. Скачай `LogVault-Setup-*-x64.exe` из последнего релиза.
2. Запусти установщик.
3. Открывай LogVault из Start menu.

macOS:

1. Скачай `LogVault-macos-arm64.dmg` из последнего релиза.
2. Открой DMG и перетащи `LogVault.app` в Applications.
3. Если Gatekeeper блокирует неподписанное приложение, нажми правой кнопкой по приложению и выбери Open.

Если macOS пишет, что приложение повреждено после скачивания с GitHub, сними quarantine-флаг:

```bash
xattr -dr com.apple.quarantine /Applications/LogVault.app
```

## Arch Linux

AppImage не нужен. В релизе есть Arch-пакет:

```bash
sudo pacman -U logvault-bin-*-x86_64.pkg.tar.zst
```

Он ставит бинарник и desktop launcher, после чего LogVault появляется в меню приложений.

Portable-вариант тоже есть. Скачай `LogVault-linux-x64-portable`, `install_linux_desktop.sh` и `logvault.svg` из релиза:

```bash
chmod +x LogVault-linux-x64-portable install_linux_desktop.sh
./install_linux_desktop.sh ./LogVault-linux-x64-portable
```

Будет установлено:

```text
~/.local/bin/LogVault
~/.local/share/applications/logvault.desktop
~/.local/share/icons/hicolor/scalable/apps/logvault.svg
```

После этого LogVault появится в меню GNOME/KDE/Xfce. Если меню не обновилось сразу, сделай logout/login.

Source-based Arch-пакет:

```bash
cd packaging/arch
makepkg -si
```

## Сборка single-file бинарников

PyInstaller собирает бинарник под текущую ОС. Windows `.exe` нужно собирать на Windows, Linux binary на Linux, macOS binary на macOS.

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Linux/macOS:

```bash
chmod +x scripts/build_unix.sh
./scripts/build_unix.sh
```

GitHub Actions собирает Windows, Linux, macOS, установщик, app bundle и Arch package на tag:

```bash
git tag v0.7.1
git push origin v0.7.1
```

## Тесты

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

## Лицензия

LogVault распространяется как open source под [MIT License](LICENSE).
