# ThorFG

Управление нативным ARM64 LSFG-VK через Decky для **AYN Thor Pro / Snapdragon 8 Gen 2 /
Adreno 740 / ArmadaOS**. Проект находится на стадии **0.1.0-dev**.
Frontend и backend проверяются локально; работоспособность FG на Thor ещё не подтверждена.

Реализованы профили Steam-игр, x2/x3/x4, Flow Scale, Performance Mode, поиск EXE,
проверка runtime/DLL, установка локальной сборки, переключение слотов, резервные копии,
откат и обезличенный диагностический отчёт. Изменение TOML не называется работающей FG.
Имена EXE из библиотеки являются кандидатами: реальный процесс игры нужно проверить.

Проект не требует изменения ABL, Android, разметки или системного Vulkan-драйвера.
Steam Launch Options остаются под управлением пользователя/Armada. Lossless.dll и
другие платные файлы не поставляются. Нужна собственная копия Lossless Scaling.

## Начать на Windows

**PowerShell, каталог проекта:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location plugin
npm ci --ignore-scripts
npm run typecheck
npm run build
Set-Location ..
.\.venv\Scripts\python.exe scripts/package_plugin.py
.\.venv\Scripts\python.exe scripts/package_source.py
```

Результат — `artifacts/ThorFG-dev.zip` и файл SHA-256. Это тестовый пакет управляющего
плагина; библиотека ARM64 собирается отдельно на Linux ARM64.

## Перед установкой на Thor

В терминале ArmadaOS выполните одну команду из каталога исходников:

```bash
bash scripts/collect-device.sh
```

Сначала сравните сведения с [результатами исследования](docs/RESEARCH.md).
Затем используйте [сборку](docs/BUILD_RU.md), [установку](docs/INSTALL_RU.md)
и [проверку на устройстве](docs/DEVICE_TESTING_RU.md).
При существующем ArmadaLSFG запись общей конфигурации блокируется: оба менеджера
не должны одновременно изменять conf.toml.

## Структура и ограничения

| Каталог | Содержимое |
|---|---|
| plugin/src | Интерфейс Decky React/TypeScript |
| plugin/backend/thorfg | Профили, Steam, runtime, TOML, транзакции и диагностика |
| runtime | Закреплённые исходники и рецепт сборки |
| scripts | Установка/удаление, упаковка, сбор сведений |
| tests | Проверки во временных каталогах |
| docs | Аудит, архитектура, руководства и фактическая валидация |

Слоты runtime глобальные: включённые профили должны ссылаться на активный слот.
Удаление runtime снимает регистрацию слоя и выключает наши профили; артефакты и история
остаются для восстановления. Поддерживается безопасное копирование выключенных чужих
профилей только при точном совпадении названия профиля и установленной игры.
Автоматическое обновление из сети и присвоение статуса Known Good пока не предусмотрены.

Локальная сборка современной 2.0.0 отделена от исторического GPL runtime: у неё другая
лицензия и другая DLL. Подробности — в [SOURCE_PROVENANCE.md](SOURCE_PROVENANCE.md)
и [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Отчёт о реально выполненных проверках — [docs/VALIDATION_RU.md](docs/VALIDATION_RU.md).
