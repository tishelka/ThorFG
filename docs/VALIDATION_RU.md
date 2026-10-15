# Фактически выполненные проверки

## Исправление HOME/XDG и CI — 2026-10-15

Исходный commit: `161afd39e666f0e9bdb440feedc0d8a4c7b403f7`.
Прочитаны jobs и полный лог Ubuntu из
[запуска 38740664790](https://github.com/tishelka/ThorFG/actions/runs/38740664790).
Подтверждено: frontend success, Ubuntu backend failure в `Plugin._main()`;
Windows unittest success, но итоговый job отмечен cancelled после падения матрицы.
Ubuntu выполнил 52 теста, из них 51 успешно и один с ThorError.

Причина: mock Decky задавал временный DECKY_USER_HOME, но fixture не изолировала
XDG_CONFIG_HOME/XDG_DATA_HOME runner. Конструктор получал чужой абсолютный каталог,
и guarded() правильно запрещал выход за тестовый HOME. Другие аргументы fixture
уже были внутри канонического HOME. Исходный лог не содержит конкретных значений XDG;
их значения на старом runner не заявляются известными. До исправления локально
воспроизведён тот же traceback при подстановке абсолютных runner XDG вне временного HOME.

Исправление тестов: patch HOME/USERPROFILE/XDG на временные каталоги с восстановлением
после каждого теста; глобальная среда workflow не очищается. Отдельный шаг CI запускает
RPC-тест из заведомо чужого runner HOME/XDG и требует успеха.

Дополнительно устранён production-дефект: исходный префикс явно объявленного HOME
терялся при resolve(), из-за чего DECKY_HOME/XDG через тот же системный alias
отклонялись. Теперь канонизируется только этот доверенный префикс. Дочерние symlink,
посторонние alias, абсолютные пути вне HOME и `..` по-прежнему запрещены.

### Локально выполнено на Windows

* pip install -r requirements.txt, compileall — успешно.
* unittest: **67 тестов, 60 успешных, 7 пропущенных** только из-за Windows error 1314
  (нет права создавать symlink). Любая ошибка symlink в Linux считается ошибкой теста.
* Дополнительный RPC-тест с чужими HOME/XDG — успешен.
* npm ci --ignore-scripts, typecheck, build, test:bundle — успешно; npm audit: 0.
* bash -n scripts/collect-device.sh через Git Bash — успешно.
* package_plugin.py — успешно; SHA файлов итогового ZIP проверены, его установка,
  удаление и rollback выполнены в изолированном HOME. Runtime/DLL в ZIP отсутствуют.

### GitHub Actions после исправления

Подтверждён [запуск 38743041062](https://github.com/tishelka/ThorFG/actions/runs/38743041062)
для исправляющего commit **85ccf7c17216fbacda5bbea52e9f3c635d0731d8**, ветка
`fix/xdg-home-ci`, [черновой PR №1](https://github.com/tishelka/ThorFG/pull/1).
Получены завершённые jobs и прочитаны логи обоих backend:

| Job | Результат |
|---|---|
| backend (ubuntu-latest) | SUCCESS: 67/67 тестов, без пропусков; дополнительный RPC-тест с чужими HOME/XDG успешен; bash -n успешен |
| backend (windows-latest) | SUCCESS: 67/67 тестов, без пропусков; дополнительный RPC-тест с чужими HOME/XDG успешен |
| frontend | SUCCESS: npm ci, typecheck, build, test:bundle, ZIP и upload artifact |

В отличие от локального Windows-хоста, оба runner разрешили создание symlink:
все позитивные и негативные сценарии реальной файловой системы исполнились.
Workflow не отключает тесты и не использует continue-on-error. Проверка относится
к ветке PR: master на этом этапе остался на исходном коммите.

### Mock и аппаратные проверки

RPC проверяется с явным test stub Decky, JS — с mock globals. Новые Linux-тесты
проверяют реальную файловую семантику symlink, но не AYN Thor. На устройство
изменения не устанавливались, runtime не активировался, hardware_verified=false.
Расположение Decky в конкретной Armada, доступность Vulkan host/guest loader,
DLL negotiation и настоящая FG требуют проверки на Thor. Для первой read-only
проверки предназначен `bash scripts/collect-device.sh`, расширенный сведениями о путях.

## Первичная локальная проверка 0.1.0-dev

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
