# Установка на ArmadaOS

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

Распаковывайте в новый каталог: если `~/thorfg` уже существует, сначала сохраните или
переименуйте его. Готовый ZIP плагина переносится отдельно из **PowerShell**:

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

После BUILD_RU.md:

```bash
cd "$HOME/thorfg"
python3 scripts/thorfg.py check
python3 scripts/thorfg.py dry-run --bundle artifacts/runtime/historical --slot historical
python3 scripts/thorfg.py install --bundle artifacts/runtime/historical --slot historical
python3 scripts/thorfg.py activate --slot historical
python3 scripts/thorfg.py diagnose --export
```

Install только копирует файлы в новый именованный слот. Activate регистрирует собственный
manifest. Между этими действиями слот можно проверить. Те же действия есть в Decky → Runtime:
укажите полный локальный путь к сборке и имя слота, затем активируйте его.
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

ThorFG не перезаписывает чужие manifest и блокирует запись общей конфигурации при
обнаружении другого LSFG-менеджера. Остановка его окна недостаточна: процесс может
продолжать работу. Для осознанной миграции сначала сохраните копии конфигурации и настроек,
выгрузите другой плагин, затем переместите **его каталог плагина и настройки менеджера**
в отдельную папку резервных копий вне сканируемых каталогов. Выполняйте это вручную,
сверив фактические пути, после собственного решения о миграции.

Старый слой также нужно вручную вывести из implicit_layer.d в резервную папку;
ThorFG не принимает владение его библиотекой. Не запускайте одновременно два менеджера.
В Diagnostics доступен ограниченный импорт: точное имя профиля = имя установленной игры,
один active_in, новый профиль выключен. Неоднозначные EXE укажите вручную.
Чужие исходные профили остаются в TOML; перед включением конфликтующего ThorFG-профиля
разрешите пересечение вручную в сохранённой копии конфигурации.
