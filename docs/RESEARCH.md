# Технический аудит ThorFG

Проверено 15 октября 2026 года. Локальное окружение: Windows x64, Python 3.12.2,
Node 20.12.1; из sandbox WSL возвращает E_ACCESSDENIED. От пользователя видны только
docker-desktop/data, Docker daemon не запущен. CMake и Linux ARM64 здесь недоступны.
Исходники пяти запрошенных репозиториев и двух официальных архивов прочитаны;
локальные копии для исследования находятся в исключённом из публикации `.research/`.

## Версии и происхождение

GitHub [PancakeTAS/lsfg-vk](https://github.com/PancakeTAS/lsfg-vk) теперь содержит
переадресацию. Официальный [новый репозиторий](https://git.lsfg-vk.dev/lsfg-vk/refs/)
имеет тег `2.0.0`: **2333707d55b68ddd8066fd95404c3b7d07e00d3a**.
[Объявление стабильной версии](https://lsfg-vk.dev/blog/release-v2.0.0/)
датировано 2026-09-05. Это отдельная история, не тег `v2.0.0-dev`.
На момент аудита master: `eb080c933da9612d70ed12d15610f808b76f108b`,
также существует ветка mangohud-integration. Эти подвижные ветки не используются сборкой.

[Архив](https://git.lsfg-vk.dev/lsfg-vk-archive/) содержит develop/release,
теги v0.9.0, v1.0.0, v2.0.0-dev. Последний develop и историческая отправная точка
совпадают: **8b0da2661c6f3473a7fccc8ba643880050e71642**.
Рецепт ThorFG по умолчанию повторяет именно эту ревизию без патчей.
Это «исторический кандидат», а не Known Good для Thor.

В [SOURCE.md Zensenshi](https://github.com/Zensenshi/lsfg-vk-odin2-armada/blob/main/SOURCE.md)
зафиксированы эта ревизия, Fedora Distrobox, clang 22.1.8 и SHA-256
`dc08b91937c998f30115f1fac48ffe40d5142ce8e80e4b68feb3fef6b675e804`.
Автор сообщает о тесте Odin 2 Portal/Adreno 740, но не Thor Pro.
Причина выбора коммита сверх воспроизведения собственного проверенного артефакта
не документирована; мы её не приписываем автору. В архиве более свежего develop нет.
В новой истории после 2.0.0 появились исправления lifetime контекста, DLL negotiation
и работа с цветом; их влияние на Turnip здесь не проверено.

## Что подтверждают исходники

* [CMake исторического коммита](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/CMakeLists.txt?id=8b0da2661c6f3473a7fccc8ba643880050e71642):
  C++20, отдельные common/backend/layer/CLI, UI отключается. Слой — shared library,
  статические common/backend попадают внутрь. Жёстких SSE/AVX-флагов или x86 intrinsics
  в исследованных runtime-файлах не найдено. Это не доказательство переносимости всех путей.
* [Vulkan wrapper](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/lsfg-vk-common/src/vulkan/vulkan.cpp?id=8b0da2661c6f3473a7fccc8ba643880050e71642)
  загружает libvulkan.so через dlopen, запрашивает Vulkan 1.2, проверяет shaderFloat16.
  CPU-библиотека должна соответствовать loader ABI: для нативного ARM64 loader нужен AArch64 ELF.
  Версия api_version в JSON (1.4.328) не является доказательством требования GPU Vulkan 1.4.
* [DLL reader](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/lsfg-vk-backend/src/extraction/dll_reader.cpp?id=8b0da2661c6f3473a7fccc8ba643880050e71642)
  и shader_registry извлекают shader-данные из собственной Lossless.dll пользователя;
  DLL не исполняется как нативная ARM64-библиотека. ThorFG её не поставляет.
* [Manifest](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/lsfg-vk-layer/VkLayer_LSFGVK_frame_generation.json.in?id=8b0da2661c6f3473a7fccc8ba643880050e71642)
  объявляет GLOBAL implicit layer, отключаемый DISABLE_LSFGVK=1. Установка JSON в
  пользовательский implicit_layer.d обеспечивает обнаружение нативным loader без Launch Options.
  Перехват swapchain/present находится в lsfg-vk-layer. Отсутствие профиля отключает FG для процесса.
* [Detection](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/lsfg-vk-common/src/configuration/detection.cpp?id=8b0da2661c6f3473a7fccc8ba643880050e71642)
  проверяет LSFGVK_PROFILE, суффикс /proc/self/exe, Wine .exe из maps и comm.
  Сравнение чувствительно к регистру, comm может быть усечён Linux.
  Поэтому обнаруженный EXE — кандидат; пользователь должен сверить его с реальным процессом.
* [Config](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/lsfg-vk-common/src/configuration/config.cpp?id=8b0da2661c6f3473a7fccc8ba643880050e71642)
  требует version=2, [global], [[profile]], active_in (строка/массив), multiplier>1,
  flow_scale 0.25..1.0, performance_mode, pacing='none'. Параметры окружения профиля
  в этой ревизии требуют LSFGVK_ENV; рецепт из чужого README нельзя слепо переносить.
* [Новый config.cpp](https://git.lsfg-vk.dev/lsfg-vk/tree/lsfg-vk-config/src/config.cpp?id=2333707d55b68ddd8066fd95404c3b7d07e00d3a)
  всё ещё использует version=2, но строго отвергает неизвестные ключи, удалил gpu,
  добавил pacing_mode/log_level и использует lsfg-vk.dll из ветки Steam `lsfg-vk`.
  ThorFG применяет отдельные адаптеры, не считает номер TOML достаточным для совместимости.

## Armada, FEX и Gamescope

Изучен Armada `8687635f562f6219a31999a8ef2f7048d76f1748`.
[armada-game-launch](https://github.com/virtudude/armada/blob/8687635f562f6219a31999a8ef2f7048d76f1748/system_files/usr/libexec/armada/armada-game-launch)
настраивает FEX_APP_CONFIG для различных Proton/FEX путей. ThorFG его не заменяет.
Гипотеза: если Vulkan thunk переводит вызовы к host ARM64 loader, ему достаточно ARM64 слоя.
Если игра использует guest x86 loader, нужны соответствующий guest слой и видимость manifest
в rootfs/container. Из одной модели SoC это определить нельзя. Новая upstream multilib x86
сборка не является готовым ARM64 thunk-решением. Нужны maps конкретной игры и логи loader.

Gamescope — отдельный Vulkan-процесс: попадание слоя в gamescope не доказывает FG в игре.
Исторический pacing='none' полагается на VSync; compositor может влиять на pacing
([Configuration.md](https://git.lsfg-vk.dev/lsfg-vk-archive/tree/docs/Configuration.md?id=8b0da2661c6f3473a7fccc8ba643880050e71642)).
Поддержка bindless/FP16, memory types, extensions, стабильность Turnip и задержка требуют
проверки реального драйвера. Нельзя обещать фиксированный прирост кадров.

## Decky и референс

Decky template `90d0780e882a17f5714fc6de044c645f22608290` использует @decky/api
callable/definePlugin, @decky/ui, @decky/rollup, main.py и api_version=1.
ThorFG использует эти API с flags=[] и без root. Во время установки npm обнаружены
уязвимые зависимости старого Rollup и delete/glob из @decky/rollup 1.0.2.
В ThorFG Rollup обновлён до 4.64.7, UI до 4.13.0; preset заменён явной конфигурацией
с тем же контрактом Decky globals. npm audit после замены: 0 известных уязвимостей.

ArmadaLSFG `0b74b261ea294e2df3ad9e8189f37c5137ab5dac`: BSD-3-Clause;
main.py управляет TOML-блоками, отдельными settings, EXE, /proc и пользовательским runtime.
Его код не копировался. ThorFG добавляет round-trip TOML, контроль внешних изменений,
журнал восстановления нескольких файлов, проверку provenance и локальных SHA, слоты runtime,
диагностику без выдачи конфигурации за FG. Присутствие другого менеджера блокирует запись
conf.toml. Импорт создаёт выключенную копию профиля; перенос владения чужими файлами запрещён.

## Лицензии и границы проверки

Архивный код имеет SPDX GPL-3.0-or-later. Новый код 2.0.0 — CC BY-NC-ND 4.0
([объявление](https://lsfg-vk.dev/blog/important-changes-to-lsfg-vk/), LICENSE в обоих checkout).
Собственный управляющий код отделён и лицензирован MIT. Новый runtime не включается в
пакет плагина: рецепт собирает неизменённые исходники локально, условия дальнейшего
распространения необходимо учитывать отдельно; разрешение на производные работы не заявлено.
Юридические выводы о допустимости конкретного распространения здесь не делаются.

Не проверены: ARM64-компиляция на этом Windows-хосте, загрузка Decky в Game Mode,
доступность host-layer в FEX/Proton, DLL конкретной версии Steam, FG, frametime/latency,
отключение на живой игре. Отсутствие доступа к Thor не заменяется mock-статусом.
