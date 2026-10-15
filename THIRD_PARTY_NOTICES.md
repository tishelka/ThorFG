# Сторонние компоненты

Собственный код ThorFG: MIT, см. LICENSE. Это не меняет лицензии перечисленных компонентов.

* Исторический LSFG-VK, PancakeTAS и участники, commit
  `8b0da2661c6f3473a7fccc8ba643880050e71642`: GPL-3.0-or-later по SPDX исходников.
  Источник: https://git.lsfg-vk.dev/lsfg-vk-archive/ . Его код не включён в пакет
  плагина; runtime собирается отдельно. Рецепт сохраняет UPSTREAM-LICENSE.
  При распространении GPL-бинарника необходимо предоставить соответствующие исходники
  и сохранить уведомления/условия upstream, а не ограничиваться названием ThorFG.
* Современный LSFG-VK 2.0.0, PancakeTAS: CC-BY-NC-ND-4.0,
  https://git.lsfg-vk.dev/lsfg-vk/tree/LICENSE.txt?id=2333707d55b68ddd8066fd95404c3b7d07e00d3a .
  Не входит в ZIP ThorFG. Автоматическая публикация этого runtime не реализована.
* Lossless Scaling, THS: коммерческий продукт. Пользователь предоставляет собственную
  установленную копию. DLL, модели и извлечённые шейдеры не включены ни в один пакет ThorFG.
* tomlkit 0.13.3: MIT, Copyright (c) 2018 Sébastien Eustace;
  https://github.com/python-poetry/tomlkit . При упаковке сохраняется оригинальный LICENSE.
* @decky/api и @decky/ui: BSD-3-Clause, SteamDeckHomebrew contributors;
  https://github.com/SteamDeckHomebrew . UI и React предоставляет Decky, @decky/api
  включён в JS. Копии лицензий всех включённых npm-компонентов сохраняются в ZIP.
* react-icons: MIT; используемая иконка Font Awesome — CC BY 4.0, Fonticons, Inc.,
  https://fontawesome.com/license/free . Не заявляется авторство графического символа.
* tslib: 0BSD, Microsoft Corporation. Копия лицензии сохраняется в ZIP.
* Rollup, TypeScript и плагины сборки — инструменты разработки с отдельными лицензиями;
  установленные версии и integrity доступны в plugin/package-lock.json.

Zensenshi/lsfg-vk-odin2-armada (GPL) и BakaPute/ArmadaLSFG (BSD-3-Clause) прочитаны
как технические референсы. Их installer/backend/frontend не скопированы.
Decky template (BSD-3-Clause) использован для изучения API и контракта загрузчика;
генератор конфигурации @decky/rollup не включён в ThorFG.
