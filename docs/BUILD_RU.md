# Сборка

## Управляющий плагин: Windows PowerShell

Из `D:\projects\thorfg` выполните команды README. Нужны Python 3.11+ (проверено 3.12)
и Node.js 20+. Используется npm lockfile. `npm ci --ignore-scripts` не запускает
install scripts зависимостей. Скрипт упаковки переносит tomlkit с его лицензией.
Frontend содержит только штатные Decky globals и JS backend RPC.

## ARM64 runtime: терминал ArmadaOS или SSH на Thor

Сначала выполните сбор сведений из DEVICE_TESTING_RU.md. Предполагаются доступные
`python3`, `distrobox` и настроенный контейнерный движок. Это проверяется до сборки.

Из корня исходников:

```bash
python3 runtime/build.py --variant historical
```

Скрипт проверяет Linux ARM64, создаёт пользовательский контейнер `thorfg-build-f44`
из `registry.fedoraproject.org/fedora:44`, затем запускает свою копию внутри него.
`sudo dnf install` выполняется только внутри контейнера. Компиляторы не устанавливаются
в неизменяемую часть Armada. Потребуются сеть, несколько ГБ диска и время на компиляцию.
Скрипт скачивает git-исходники, не выполняет `curl | bash` или чужой installer.

Результат: `artifacts/runtime/historical/` — .so, JSON, UPSTREAM-LICENSE,
опциональный CLI, build-report.json и SHA256SUMS.
Исходники сборки находятся в `.build/historical`. Существующие каталоги не очищаются:
для повторной независимой сборки используйте новую копию исходников ThorFG.
Не удаляйте рабочие каталоги рекурсивно по непроверенному пути.

## Отдельный современный эксперимент

После успешной сборки исторического варианта:

```bash
python3 runtime/build.py --variant stable
```

Этот рецепт собирает 2.0.0 commit `2333707d…`, а не плавающий master.
Нужна DLL `lsfg-vk.dll` из ветки `lsfg-vk` в свойствах Lossless Scaling Steam.
Исторический runtime ожидает `Lossless.dll`; нельзя автоматически смешивать эти варианты.
Новая лицензия не равна GPL, подробности в THIRD_PARTY_NOTICES.md.
Ни один из рецептов пока не исполнялся на Thor в рамках разработки этого проекта.

## Проверка результата: внутри Fedora Distrobox

```bash
cd "$HOME/thorfg"
file artifacts/runtime/historical/liblsfg-vk-layer.so
readelf -h artifacts/runtime/historical/liblsfg-vk-layer.so
readelf -d artifacts/runtime/historical/liblsfg-vk-layer.so
cd artifacts/runtime/historical
sha256sum -c SHA256SUMS
```

В выводе ожидаются ELF64, DYN и AArch64. `readelf -d` показывает NEEDED: проверяйте
доступность соответствующих libstdc++/libc в host Armada, а не только в контейнере.
В частности, новый Fedora toolchain может требовать более свежий GLIBC/GLIBCXX.
После установки проверяется loader именно **в терминале Armada вне Distrobox**.
Успех CMake не доказывает ни host ABI-совместимость, ни FG.

Для проверки ABI на host можно использовать `readelf --version-info` и сравнить с
установленными библиотеками; не запускайте `ldd` для бинарников неизвестного происхождения.
Рецепт фиксирует SHA исходников и записывает версии инструментов; byte-for-byte
воспроизводимость ещё требует фиксации digest контейнера и набора RPM.
