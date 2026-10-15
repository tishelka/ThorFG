# Сборка

## Сначала использовать уже готовый build-llvm

Владелец Thor сообщил об успешной сборке исторического коммита в
`~/thorfg/.build/historical/build-llvm`. Её не нужно скачивать и компилировать повторно.
Сначала сохраните локальный diff и обновите ThorFG по THOR_REAL_DEVICE_PROGRESS_RU.md.

**SSH на Thor, после безопасного обновления:**

```bash
cd "$HOME/thorfg"
distrobox enter --name thorfg-build-f44 -- python3 "$HOME/thorfg/runtime/build.py" \
  --variant historical --package-existing \
  --use-existing-checkout "$HOME/thorfg/.build/historical" \
  --build-dir "$HOME/thorfg/.build/historical/build-llvm" \
  --expected-sha256 f01502a88d2991b23db12251264dd59561448846fbcf7f6f91007b95973f581f
```

Этот SHA относится только к сообщённой владельцем сборке. Для другого результата
укажите его фактический хеш. Здесь нет dnf, fetch/clone, configure или build.
Проверка Git выполняется с GIT_NO_LAZY_FETCH=1: недостающие объекты приводят к отказу,
а не скрытой сетевой загрузке.

Сборщик требует точный commit и tree, разрешённый origin, неизменённые tracked-файлы,
отсутствие посторонних untracked-файлов (кроме явно выбранного build directory),
корректный CMake cache, сохранённые данные Clang, Ninja link entry, ELF64/DYN/AArch64,
manifest и Vulkan negotiation export. При недостатке данных он останавливается.
Сведения CMake/Ninja — локальные свидетельства, не криптографическое доказательство
соответствия машинного кода исходникам. Явный SHA связывает операцию с вашим результатом.

Результат: `artifacts/runtime/historical/` содержит .so, manifest, UPSTREAM-LICENSE,
build-report.json, SHA256SUMS и опционально CLI. Отчёт содержит source tree/origin,
записанную версию компилятора, версию cache и версии инструментов, **наблюдаемые при
упаковке**, а не приписанные историческому запуску. SHA256SUMS покрывает и build-report.json,
но не сам себя. Проверка пакета совместна с backend inspect_bundle().

Если каталог результата уже существует, ничего не перезаписывается. Укажите, например,
`--output "$HOME/thorfg/artifacts/runtime-recovered"`; вариант historical добавится внутрь.
Это упаковка, не активация и не регистрация слоя.

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
В зависимости включён пакет **llvm**, а не только clang/lld. Перед configure проверяются
clang++, llvm-ar, llvm-ranlib, cmake, ninja, readelf, nm и file. CMake получает абсолютные
CMAKE_AR/CMAKE_RANLIB/CMAKE_CXX_COMPILER_AR/CMAKE_CXX_COMPILER_RANLIB.
Скрипт скачивает git-исходники, не выполняет `curl | bash` или чужой installer.

Результат: `artifacts/runtime/historical/` — .so, JSON, UPSTREAM-LICENSE,
опциональный CLI, build-report.json и SHA256SUMS.
Исходники сборки находятся в `.build/historical`. Существующие каталоги не очищаются:
для независимой сборки укажите новый каталог. Основной build directory теперь `build-llvm`.
Не удаляйте рабочие каталоги рекурсивно по непроверенному пути.

Официальный архив и явно разрешённое зеркало GitHub проверяются по одинаковому
commit/tree. При неудаче загрузки частичный checkout сохраняется, следующий источник
использует отдельный каталог. Для historical можно предпочесть проверенное зеркало:

```bash
python3 runtime/build.py --variant historical --source https://github.com/eugeniosegala/lsfg-vk-experimental.git
```

Для исходников, которые уже находятся на диске, но ещё требуют сборки:

```bash
python3 runtime/build.py --variant historical \
  --use-existing-checkout "$HOME/thorfg/.build/historical" \
  --build-dir "$HOME/thorfg/.build/historical/build-llvm-new"
```

`--resume` явно разрешает повторный configure/build существующего корректного build directory.
Cache с `-NOTFOUND` не удаляется и не чинится скрыто: выберите новый --build-dir.
Без --resume существующий результат не пересобирается. Для готового build-llvm используйте
--package-existing. Все варианты сохраняют stable и historical раздельно.

## Отдельный современный эксперимент

После успешной сборки исторического варианта:

```bash
python3 runtime/build.py --variant stable
```

Этот рецепт собирает 2.0.0 commit `2333707d…`, а не плавающий master.
Нужна DLL `lsfg-vk.dll` из ветки `lsfg-vk` в свойствах Lossless Scaling Steam.
Исторический runtime ожидает `Lossless.dll`; нельзя автоматически смешивать эти варианты.
Новая лицензия не равна GPL, подробности в THIRD_PARTY_NOTICES.md.
Новый автоматизированный путь восстановления требует проверки на устройстве;
успех старой ручной компиляции подтверждён сообщением владельца, см. отдельный протокол.

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
