# Продолжение испытаний на реальном Thor

## 1. Безопасно обновить существующий checkout

Уже собранную `.build/historical/build-llvm/lsfg-vk-layer/liblsfg-vk-layer.so`
сохраняем и используем без повторного clone/configure/build.
Следующие команды выполняются **в Windows PowerShell**, в локальном ThorFG.
Получите ветку PR в чистом локальном checkout (при локальных изменениях сначала
сохраните их обычным Git workflow):

```powershell
git status --short
git fetch origin
git switch feat/runtime-recovery-probe
$SSH_USER = 'armada'
$SSH_HOST = Read-Host 'IP Thor'
$REMOTE_REPO = '/var/home/armada/thorfg'
$Thor = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '.\scripts\thor.ps1',
          '-SSHUser', $SSH_USER, '-SSHHost', $SSH_HOST, '-RemoteRepo', $REMOTE_REPO)
powershell @Thor -Action update -Ref feat/runtime-recovery-probe
```

IP задаётся параметром и не сохраняется приложением. После слияния PR можно
использовать `-Ref master`. На Thor helper сначала проверяет путь/origin и сохраняет
`runtime/build.py`, `runtime/sources.lock.json`, полный tracked diff и сведения об
исходной ветке в `.build/update-backups/<дата-id>/`. При успешном fetch локальные
tracked-изменения сохраняются отдельным Git stash **без untracked/ignored файлов**;
stash SHA записан в `update.json`. Затем создаётся новая тестовая ветка на выбранном
commit. Исходная ветка, stash, `.build` и `build-llvm` сохраняются. Старый diff не
применяется автоматически поверх нового сборщика. При ошибке ничего не очищайте:
прочитайте сообщение и `update.json`; не выполняйте reset --hard/clean или stash pop
вслепую. Конфликтующий untracked-файл останавливает переключение Git.

## 2. Упаковать уже готовую ARM64-библиотеку

```powershell
$BUILD_SHA = 'f01502a88d2991b23db12251264dd59561448846fbcf7f6f91007b95973f581f'
powershell @Thor -Action package-runtime -ExpectedSha256 $BUILD_SHA
powershell @Thor -Action check -ExpectedSha256 $BUILD_SHA
```

Первая команда выполняет `--package-existing` внутри уже существующего Distrobox
`thorfg-build-f44`; она не устанавливает RPM, не загружает исходники и не компилирует.
Проверяются точные commit/tree/origin, чистота source, ELF, manifest, LLVM CMake cache,
завершённая Ninja link-запись и ожидаемый SHA. При недостатке доказательств операция
останавливается с ошибкой. SHA выше относится только к сообщённой пользователем
сборке, а не ко всем будущим сборкам.

Результат на Thor: `artifacts/runtime/historical/` с `.so`, manifest, лицензией,
`build-report.json`, `SHA256SUMS` и CLI при наличии. Эти команды **не активируют** слой.
Если выходной каталог уже существует, он не заменяется. Выберите новое назначение:
`powershell @Thor -Action package-runtime -ExpectedSha256 $BUILD_SHA -RuntimeOutput artifacts/runtime-recovered`.
Подробности происхождения и границ проверки — [BUILD_RU](BUILD_RU.md).

## 3. Подготовить и установить только Decky-плагин

В Windows, корень проекта (если `.venv` отсутствует, сначала `python -m venv .venv`):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location plugin
npm ci --ignore-scripts
npm run typecheck
npm run build
npm run test:bundle
Pop-Location
.\.venv\Scripts\python.exe scripts/package_plugin.py
powershell @Thor -Action deliver-plugin
powershell @Thor -Action install-plugin
```

Вместо локальной сборки можно скачать artifact **ThorFG-dev** из успешного GitHub
Actions для ветки PR, распаковать его и передать `-Package <путь/ThorFG-dev.zip>` при
`deliver-plugin`. Helper сверяет локальный и удалённый SHA перед отдельной установкой.
Установка использует прежние проверки владения каталогом ThorFG; чужой плагин она
не заменяет. Перезагрузите ThorFG в Decky доступным в вашей версии способом.

Runtime/Diagnostics должны показать ARM64 build, отдельные состояния bundle/slot/
activation, сторонние ArmadaLSFG/Decky LSFG-VK и архитектуры x86_64/i386. Пока они
присутствуют, ожидается безопасный read-only mode: просмотр и диагностика доступны,
запись общего TOML и активация слоя заблокированы. Импорт проверенного bundle в
**новый** слот ThorFG позднее возможен отдельно, без Activate.

## 4. Явные активные проверки вне контейнера

```powershell
powershell @Thor -Action host-load -ExpectedSha256 $BUILD_SHA
powershell @Thor -Action loader -ExpectedSha256 $BUILD_SHA
```

По умолчанию `check` только читает файлы. Эти два режима запускают отдельный native
процесс на host ArmadaOS с тайм-аутом 15 секунд. Loader получает временные manifest,
TOML, cache и `LSFGVK_ENV=1` только в окружении дочернего процесса. Общие файлы и
Steam Launch Options не меняются. Положительный CDLL/loader результат относится к
конкретному SHA; он не подтверждает swapchain initialization или FG.

Когда открыт **графический Desktop Mode** на Thor, установлен локальный `vkcube` и
найдена собственная подходящая `Lossless.dll`, можно отдельно выполнить:

```powershell
powershell @Thor -Action cube -ExpectedSha256 $BUILD_SHA
```

Тест ограничен 120 кадрами/тайм-аутом. SSH helper не запускает графическую сессию:
при отсутствии DISPLAY выбирается только единственный Wayland-сокет текущего
пользователя. При неоднозначности явно передайте, например, `-WaylandDisplay wayland-0`,
сверив имя с текущей Desktop-сессией. Не запускайте от root и не подбирайте DISPLAY
других пользователей. Наличие слоя и выбор environment-профиля не равны FG.
Для historical нужна `Lossless.dll`; для stable — отдельная `lsfg-vk.dll`.
Ошибка `vkCreateSwapchainKHR` в `vulkaninfo --summary` сама по себе не доказывает
несовместимость Turnip. После cube необходим отдельный документированный игровой
тест с измерением настоящих/сгенерированных кадров и frametime.

## Что уже подтверждено владельцем устройства

Ниже результаты, переданные пользователем; Codex их не повторял по SSH.

| Этап | Результат |
|---|---|
| Устройство | AYN Thor Pro, Snapdragon 8 Gen 2 / Adreno 740, AArch64 |
| Host | ArmadaOS 20261010.c3d178c, Fedora 44; Turnip Mesa 26.2.4, Vulkan 1.4.341 |
| Checkout | historical 8b0da2661c6f3473a7fccc8ba643880050e71642 получен через GitHub mirror |
| Сборка | Clang/LLVM 22.1.8, CMake 4.3, Ninja; ELF64 DYN AArch64, SHA указан выше |
| Native load | ctypes.CDLL RTLD_NOW/LOCAL успешен на host glibc 2.43 / libstdc++ 16.2.1; требуемая GLIBC ≤ 2.38 |
| Loader export | vkNegotiateLoaderLayerInterfaceVersion экспортирован |
| Loader insertion | Instance и device layer вставлены при LSFGVK_ENV=1; Turnip Adreno 740 обнаружен |
| Обычный vkcube | Работает в Desktop Mode |
| vkcube с ThorFG, runtime initialization, игра/FG | **Требует реальной проверки** |

Hardware Verified остаётся false. x2/x3/x4 на Adreno 740 не заявлены.

## Сосуществование и будущая миграция

На текущем этапе оставьте сторонние `.so`, JSON, плагины и общий TOML на месте.
Проверьте работу прежних игр после установки одного ThorFG UI. Возможная будущая
миграция требует отдельного решения: сначала установить назначение x86/i386 слоёв
для FEX/Proton, сохранить их файлы/хеши, TOML, версии плагинов и Launch Options,
согласовать точный способ отключения с владельцем ArmadaLSFG и подготовить обратное
восстановление тех же файлов/настроек. Только затем тестировать один manager/layer
в конкретной игре. Эти действия helper не выполняет; обход conflict guards не нужен.
