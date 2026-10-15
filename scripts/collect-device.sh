#!/usr/bin/env bash
set -euo pipefail
printf '=== ThorFG: сведения об устройстве (без изменений системы) ===\n'
uname -sm
if [[ -r /etc/os-release ]]; then
    cat /etc/os-release
fi
printf '\n=== Доступные инструменты ===\n'
for tool in python3 distrobox vulkaninfo FEXInterpreter gamescope; do
    command -v "$tool" || true
done
printf '\n=== Пользовательские пути (проверка без записи) ===\n'
if command -v python3 >/dev/null 2>&1; then
    project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
    python3 - "$project_root" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[1]) / "plugin/backend"))
from thorfg.paths import Paths, ThorError
from thorfg.steam import Steam

declared_home = Path(os.environ.get("DECKY_USER_HOME") or Path.home())
decky_home = os.environ.get("DECKY_HOME")
try:
    paths = Paths.environment(declared_home, Path(decky_home) if decky_home else None)
    def display(path):
        if path == paths.home:
            return "~"
        return "~/" + path.relative_to(paths.home).as_posix() if path.is_relative_to(paths.home) else "<внешний каталог>"
    print("HOME: ~; системный alias:", declared_home != paths.home)
    print("Источник HOME:", "DECKY_USER_HOME" if os.environ.get("DECKY_USER_HOME") else "окружение текущей сессии")
    for label, path in (("Decky", paths.decky_root), ("Конфигурация", paths.config),
                        ("Vulkan manifest", paths.manifest), ("Runtime", paths.runtimes)):
        print(label + ":", display(path), "(существует)" if path.exists() else "(не существует)")
    if not decky_home:
        print("DECKY_HOME не задан в этой сессии; ~/homebrew — предполагаемый путь, не подтверждение настроек loader")
    steam = Steam(paths.home)
    libraries = steam.libraries()
    print("Steam libraries:", len(libraries), "; вне HOME:", sum(not p.is_relative_to(paths.home) for p in libraries))
    for warning in steam.warnings:
        print("Steam:", warning)
except (OSError, ValueError, ThorError) as exc:
    print("Проверка путей остановлена:", exc, file=sys.stderr)
    raise SystemExit(1)
PY
else
    printf 'python3 отсутствует; проверка модели путей не выполнена\n'
fi
printf '\n=== Vulkan ===\n'
if command -v vulkaninfo >/dev/null 2>&1; then
    # Выводим только версии, GPU, драйвер и LSFG-слои, не произвольные environment.
    vulkaninfo --summary 2>/dev/null | sed -nE '/Vulkan Instance Version|deviceName|driverName|driverInfo|VK_LAYER_.*LSFG/p' || true
fi
printf '\n=== Decky ===\n'
if [[ -d "$HOME/homebrew/plugins" ]]; then
    printf 'Пользовательский каталог homebrew/plugins существует\n'
else
    printf 'Стандартный пользовательский каталог Decky не найден\n'
fi
