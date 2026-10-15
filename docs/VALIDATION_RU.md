# Фактически выполненные проверки

Дата: 2026-10-15. Хост: Windows x64, Python 3.12.2, Node.js 20.12.1, npm 10.5.0.
Это отчёт о локальной разработке, не о тестировании AYN Thor Pro.

| Проверка | Результат |
|---|---|
| Python unittest | 52 теста: 51 успешный, 1 пропущен |
| Пропущенная проверка | Создание symlink недоступно этому пользователю Windows; тест включён в Linux CI |
| Python compileall | Backend, main.py, scripts, runtime: успешно |
| TypeScript tsc --noEmit | Успешно |
| Rollup production build | Успешно, без unresolved dependencies |
| Загрузка итогового JS с явными mock Decky globals | Успешно, 1 тест; сверены имена RPC с backend |
| npm audit | 0 известных уязвимостей после обновления Rollup и удаления delete/glob preset |
| bash -n collect-device.sh через Git Bash | Успешно; Linux-команды на Thor не исполнялись |
| Референсная .so Zensenshi | ELF AArch64, SHA-256 dc08b919… совпал с SOURCE.md; это не собственная сборка ThorFG |
| ARM64 build script на Windows | Остановлен проверкой платформы до сборки, как предусмотрено |
| Реальный ThorFG-dev.zip | Проверены SHA всех файлов, наличие лицензий и vendor; установка/удаление/rollback прошли в изолированном home |
| Архив исходников | Проверены состав, отсутствие .research/.venv/node_modules/.git и SHA-256 |
| GitHub Actions | Workflow создан; удалённый запуск не выполнялся |

Backend-тесты проверяют round-trip TOML, неизвестные поля/комментарии, multiline strings,
семантическую валидацию, миграцию settings, выключенные профили, дубликаты и пересечения,
backup/rollback, блокировку, внешние изменения, восстановление после ошибки до/после rename,
незавершённый журнал, ограничение путей, ZIP traversal и собственность файлов плагина.
Проверяются несколько Steam libraries, Unicode, повреждённые VDF/ACF, launcher/EXE,
отсутствие DLL/manifest, неверный ELF, SHA mismatch, неподдерживаемая ревизия, ArmadaLSFG/MAKO,
установка/активация/отключение во временном home и экспорт без личных данных.

Все ELF-файлы в этих тестах синтетические. Их проверка подтверждает поведение
валидатора, а не работоспособность LSFG-VK. Decky test stub не подтверждает запуск
плагина в Game Mode.

В процессе аудита скачаны официальные исходники и референс Zensenshi. Файлы коммерческого
Lossless Scaling не скачивались. Копии исследований исключены через .gitignore.
Проверка исходников выявила перенос upstream и отдельную стабильную 2.0.0, поэтому
сборочные рецепты используют два разных закреплённых SHA и два адаптера.

Не выполнены: ARM64-компиляция, загрузка слоя в Vulkan на Thor, DLL negotiation,
FEX/Proton integration, управление геймпадом и touch в реальном Decky,
измерение дополнительных кадров/frametime/input latency и восстановление реальной игры.
Из sandbox WSL возвращает E_ACCESSDENIED; проверка от пользователя выявила только
дистрибутивы docker-desktop/data, локальный Docker daemon не запущен. Linux ARM64 build
в этой среде не заявляется. Следующий шаг — сбор сведений по DEVICE_TESTING_RU.md.
