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
