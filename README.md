# LogVault

LogVault скачивает отчеты World of Warcraft из Warcraft Logs API v2 и сохраняет их в локальный пакет, который удобно открыть человеку или отправить на разбор.

Пакет содержит:

- `summary.md` - короткий человекочитаемый обзор отчета и выбранных боев.
- `fights.csv`, `actors.csv`, `abilities.csv` - справочники отчета.
- `tables/*.csv` и `tables/*.json` - агрегированные таблицы Warcraft Logs: урон, лечение, смерти, касты, прерывания.
- `events/*.jsonl` и `events/*.csv` - сырые события боя, по одному событию на строку.
- `.zip` рядом с папкой экспорта - один файл, который удобно отправлять.

## Установка

Нужен Python 3.10+.

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
```

Можно запускать и без установки пакета:

```bash
python3 run_gui.py
```

CLI без установки:

```bash
python3 run_cli.py REPORTCODE --fight last
```

LogVault сам пытается использовать `certifi` или системный CA bundle для запросов к Warcraft Logs. Если на macOS `pip install -e .` все равно падает с `CERTIFICATE_VERIFY_FAILED`, это проблема сертификатов Python/PyPI. Для Python с python.org запусти:

```bash
open "/Applications/Python 3.13/Install Certificates.command"
```

Если версия Python другая, замени `Python 3.13` на свою. Быстрый обходной путь для этого проекта - использовать `python3 run_gui.py`, потому что внешних Python-зависимостей у LogVault нет.

На минимальных Linux-сборках может не быть Tkinter. Тогда поставь системный пакет, например:

```bash
sudo apt install python3-tk
```

## Ключи Warcraft Logs

Warcraft Logs API v2 использует OAuth и GraphQL.

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

Полезные официальные страницы:

- [Warcraft Logs API docs](https://www.warcraftlogs.com/api/docs)
- [Warcraft Logs v2 API docs](https://www.warcraftlogs.com/v2-api-docs/warcraft/)

## Использование

GUI:

```bash
logvault-gui
```

В окне можно вставить ссылку на отчет, выбрать fight (`last`, `boss`, `all` или номер), указать папку экспорта и запустить скачивание. Нужны только `Client ID` и `Client secret`; OAuth token будет получен автоматически.

CLI:

Скачать конкретный бой из URL:

```bash
logvault "https://www.warcraftlogs.com/reports/REPORTCODE#fight=12&type=damage-done"
```

Скачать последний босс-пулл:

```bash
logvault REPORTCODE --fight last
```

Скачать все босс-пуллы отчета:

```bash
logvault REPORTCODE --fight boss
```

Скачать вообще все файты, включая треш:

```bash
logvault REPORTCODE --fight all
```

Сделать быстрый экспорт без сырых событий:

```bash
logvault REPORTCODE --events none
```

Ограничить типы событий:

```bash
logvault REPORTCODE --fight 12 --events DamageDone,Casts,Deaths,Interrupts
```

По умолчанию LogVault передает `allowUnlisted=true`, поэтому отчеты по прямой ссылке обычно доступны. Private-логи, требующие пользовательской авторизации, могут не открыться через client credentials.

## Сборка в один файл

Для Windows `.exe` нужен Windows build host. PyInstaller собирает исполняемый файл под текущую ОС, поэтому с macOS нельзя напрямую получить рабочий Windows `.exe`.

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Результат:

```text
dist\LogVault.exe
```

Через GitHub Actions Windows `.exe` собирается автоматически. Запусти workflow `Build executables` вручную или создай tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

В artifacts/release появится:

```text
LogVault-windows-x64.exe
```

Linux/macOS:

```bash
chmod +x scripts/build_unix.sh
./scripts/build_unix.sh
```

Если `pip` на macOS снова жалуется на SSL, скрипт попробует сам выставить `SSL_CERT_FILE` на системный CA bundle. Можно также явно запустить:

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem ./scripts/build_unix.sh
```

Результат:

```text
dist/LogVault
```

Также добавлен GitHub Actions workflow `.github/workflows/build.yml`: он собирает отдельные single-file артефакты для Windows, Linux и macOS. Его можно запустить вручную через `workflow_dispatch` или пушем git tag вида `v0.1.0`.

## Arch Linux

AppImage не нужен. Есть два варианта.

Установка готового Linux single-file бинарника в меню текущего пользователя:

```bash
./scripts/build_unix.sh
./scripts/install_linux_desktop.sh
```

Если бинарник скачан из GitHub Actions artifact:

```bash
chmod +x LogVault-linux-x64
./scripts/install_linux_desktop.sh ./LogVault-linux-x64
```

Скрипт установит:

```text
~/.local/bin/LogVault
~/.local/share/applications/logvault.desktop
~/.local/share/icons/hicolor/scalable/apps/logvault.svg
```

После этого LogVault появится в меню приложений GNOME/KDE/Xfce. Иногда меню обновляется после logout/login.

Нативный Arch-пакет через `makepkg`:

```bash
cd packaging/arch
makepkg -si
```

PKGBUILD рассчитан на release tag `v0.1.0` в репозитории `https://github.com/MyHeartRaces/LogVault`.

## Формат для разбора

Если нужно отправить отчет на анализ, отправляй `.zip` из папки `exports/`. Для человека сначала открывай `summary.md`, затем CSV в `tables/`. Для подробного анализа используются `events/*.jsonl`.

## Проверки

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
