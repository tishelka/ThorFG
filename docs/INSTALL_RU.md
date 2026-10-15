# Установка на ArmadaOS

Если на Thor уже есть рабочий `.build/historical/build-llvm` и ручные изменения
runtime/build.py/sources.lock.json, сначала выполните безопасное обновление из
[протокола продолжения](THOR_REAL_DEVICE_PROGRESS_RU.md). Не распаковывайте архив
поверх этого checkout и не используйте reset --hard/clean.

Первый этап — **только управляющий Decky-плагин**. При существующих ArmadaLSFG,
Decky LSFG-VK и x86/i386 слоях он должен показывать read-only mode. Активация
нативного слоя и изменение общего TOML в этот этап не входят.

Все Linux-команды ниже выполняются обычным пользователем в Konsole ArmadaOS или SSH,
**вне Distrobox**, кроме явно обозначенной сборки. `sudo` для установки ThorFG не нужен.
Сначала завершите игры. Сохраните свои текущие параметры LSFG и Launch Options вручную.

## Перенос исходников с Windows

Узнайте имя пользователя и IP в Armada.
В примере замените USER и THOR_IP фактическими значениями.

**PowerShell, корень проекта:**

```powershell
.\.venv\Scripts\python.exe scripts/package_source.py
scp artifacts/ThorFG-source.tar.gz artifacts/ThorFG-source.tar.gz.sha256 USER@THOR_IP:~/
```

Архив исключает `.research`, `.venv`, node_modules, artifacts и .build.
**Konsole или SSH на Thor:**

```bash
cd "$HOME"
sha256sum -c ThorFG-source.tar.gz.sha256
tar -xzf ThorFG-source.tar.gz
```

Этот способ предназначен только для первой установки в отсутствующий каталог.
Существующий `~/thorfg` с build-llvm обновляйте helper из протокола продолжения.
Готовый ZIP плагина переносится отдельно из **PowerShell**:

```powershell
scp artifacts/ThorFG-dev.zip artifacts/ThorFG-dev.zip.sha256 USER@THOR_IP:~/thorfg/
```

На Thor не нужно копировать `.venv` из Windows — она не переносима между ОС.
Если скопирован plugin/py_modules с tomlkit, CLI использует его. Иначе создайте Linux venv:

```bash
cd "$HOME/thorfg"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Дальше команды `python3 scripts/...` используют скопированный plugin/py_modules;
при его отсутствии заменяйте `python3` на `.venv/bin/python`.

## Установить только Decky-плагин

**Терминал ArmadaOS:**

```bash
cd "$HOME/thorfg"
sha256sum -c ThorFG-dev.zip.sha256
python3 scripts/decky_plugin.py install --package ThorFG-dev.zip
```

Каталог по умолчанию — `~/homebrew/plugins/ThorFG`. Для иного фактического расположения
передайте `--decky-home /абсолютный/путь/homebrew` внутри домашнего каталога.
Откройте меню Decky и перезагрузите плагин доступным в вашей версии Decky способом.
Если такого действия нет, выполните обычную перезагрузку устройства через меню Armada.
Глобальные обновления системы и изменение служб для этого не требуются.

## Установить ARM64 runtime

После BUILD_RU.md можно импортировать bundle в новый слот без активации:

```bash
cd "$HOME/thorfg"
python3 scripts/thorfg.py check
python3 scripts/thorfg.py dry-run --bundle artifacts/runtime/historical --slot historical
python3 scripts/thorfg.py install --bundle artifacts/runtime/historical --slot historical
python3 scripts/thorfg.py diagnose --export
```

Install только копирует файлы в новый именованный слот. Activate регистрирует собственный
manifest. Между этими действиями слот можно проверить. Те же действия есть в Decky → Runtime:
укажите полный локальный путь к сборке и имя слота. На текущем Thor со сторонними
слоями оставьте слот неактивным; Activate заблокирован до отдельного решения о миграции.
На устройстве без конфликтов активация — отдельная команда `activate --slot historical`.
Download/автообновление из неизвестной сети не выполняется.

CLI `check`, `dry-run`, `install`, `update`, `activate`, `rollback`, `uninstall`, `diagnose`
использует актуальный home и абсолютные XDG_CONFIG_HOME/XDG_DATA_HOME внутри home.
Dry-run ничего не записывает; diagnose записывает отчёт только с --export.

## Обновление и выбор версий

```bash
python3 scripts/thorfg.py update --bundle artifacts/runtime/stable --slot stable-candidate
python3 scripts/thorfg.py activate --slot stable-candidate
```

Перед активацией выключите все профили и завершите игры. Имя нового слота должно отличаться
от существующего. Все включённые профили должны ссылаться на один активный runtime.
Нельзя одновременно загружать две версии слоя с одним Vulkan layer name.

## Существующий ArmadaLSFG или чужой runtime

ThorFG не перезаписывает чужие manifest и блокирует запись общей конфигурации и
активацию при обнаружении другого LSFG-менеджера или слоя. Для текущего испытания
ничего не переносите, не переименовывайте и не удаляйте: x86_64/i386 слой может быть
нужен существующему FEX/Proton. Остановка окна менеджера не снимает конфликт.
UI плагина устанавливается независимо и работает в read-only mode.
План возможной будущей миграции и обязательного восстановления описан в
[протоколе продолжения](THOR_REAL_DEVICE_PROGRESS_RU.md#сосуществование-и-будущая-миграция).
Он не выполняется автоматически и не входит в текущий этап испытаний.
В Diagnostics доступен ограниченный импорт: точное имя профиля = имя установленной игры,
один active_in, новый профиль выключен. Неоднозначные EXE укажите вручную.
Чужие исходные профили остаются в TOML; перед включением конфликтующего ThorFG-профиля
разрешите пересечение вручную в сохранённой копии конфигурации.
