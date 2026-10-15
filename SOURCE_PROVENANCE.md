# Происхождение runtime

Дата аудита: 2026-10-15. **Бинарные релизы runtime ThorFG пока не созданы.**
Фикстура ELF в тестах не является runtime и не распространяется как библиотека.

| Вариант рецепта | Repository | Исходный SHA | Назначение |
|---|---|---|---|
| historical | https://git.lsfg-vk.dev/lsfg-vk-archive.git | 8b0da2661c6f3473a7fccc8ba643880050e71642 | Повторить историческую ARM64-сборку Zensenshi |
| stable | https://git.lsfg-vk.dev/lsfg-vk.git | 2333707d55b68ddd8066fd95404c3b7d07e00d3a | Отдельный локальный эксперимент с 2.0.0 |

Патчи обоих рецептов: отсутствуют. Это разные лицензии и отдельные деревья исходников.
Ревизии зафиксированы в runtime/sources.lock.json. Ветки develop/master не используются
как плавающая зависимость. Имя historical не означает Known Good на Thor.

`runtime/build.py` сохраняет commit, repository, version, adapter, license,
compiler, CMake, os-release, список RPM, SOURCE_DATE_EPOCH, file, readelf -h/-d,
SHA-256 библиотеки/manifest/лицензии/CLI в `build-report.json`.
При установке проверяются источник, адаптер, архитектура, отсутствие патчей и SHA файлов.
Присутствие отчёта не является подписью доверенного издателя.

Рецепт фиксирует исходники, но Fedora:44 и версии RPM не зафиксированы digest/lockfile.
Поэтому заявляется воспроизводимость **последовательности сборки**, не byte-for-byte
детерминизм. Для выпуска необходимо сохранить digest контейнера/набор RPM и сравнить
результаты двух чистых сборок. Нельзя ожидать SHA Zensenshi с иным toolchain.

Перед первым бинарным релизом добавить сюда фактический SHA-256, build-report,
источник/архив GPL-кода и результаты проверки Thor. До этого статус Hardware Verified
в коде всегда false. ZIP `ThorFG-dev.zip` содержит только управляющий плагин и pure Python
зависимость; ни .so, ни коммерческих DLL в нём нет.
