import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from .config import (PREFIX, defaults, migrate_settings, parse_config, render,
                     targets, validate_compatibility, validate_profile)
from .paths import Paths, ThorError
from .runtime import Runtimes, layer_conflicts, manager_conflicts
from .steam import Steam
from .storage import Store, atomic, json_bytes, read_bytes
from .diagnostics import DeviceProbe


class Service:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.store = Store(paths)
        self.runtimes = Runtimes(paths)

    def settings(self):
        raw = read_bytes(self.paths.safe(self.paths.settings))
        return migrate_settings(json.loads(raw)) if raw else defaults()

    def games(self):
        steam = Steam(self.paths.home)
        return {"games": steam.games(), "warnings": steam.warnings}

    def executables(self, appid):
        return Steam(self.paths.home).executables(appid)

    def assert_config_access(self):
        if os.environ.get("LSFGVK_CONFIG"):
            raise ThorError("LSFGVK_CONFIG переопределён; запись стандартного TOML остановлена")
        if manager_conflicts(self.paths):
            raise ThorError("Обнаружен другой менеджер LSFG; ThorFG работает с конфигурацией только на чтение")
        if layer_conflicts(self.paths)[0]:
            raise ThorError("Сторонний Vulkan LSFG обнаружен; общая конфигурация доступна только на чтение")

    def save_profile(self, appid, value):
        profile = validate_profile(appid, value)
        with self.store.lock():
            self.assert_config_access()
            previous = read_bytes(self.paths.safe(self.paths.settings))
            original = read_bytes(self.paths.safe(self.paths.config))
            settings = self.settings()
            settings["profiles"][appid] = profile
            try:
                active = self.runtimes.active()
            except (OSError, ValueError, ThorError, TypeError):
                if profile["enabled"]:
                    raise
                active = None
            enabled = [p for p in settings["profiles"].values() if p["enabled"]]
            dll = None
            adapter = active["adapter"] if active else "historical-2dev"
            if profile["enabled"]:
                if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
                    raise ThorError("Применение FG разрешено только в Linux ARM64")
                if active is None:
                    raise ThorError("Сначала установите и активируйте ARM64 runtime")
                if any(p["runtime"] != active["slot"] for p in enabled):
                    raise ThorError("Включённые профили должны использовать активный runtime")
                conflicts, _ = layer_conflicts(self.paths)
                if conflicts:
                    raise ThorError("Конфликт с другим Vulkan слоем LSFG-VK")
                document = parse_config(original)
                configured = document.get("global", {}).get("dll")
                dll = Steam(self.paths.home).dll(adapter == "stable-2.0", configured)
                if dll is None:
                    raise ThorError("Не найдена подходящая DLL из установленного Lossless Scaling")
            # Выключенный новый профиль не должен создавать upstream config с примерами.
            changes = {self.paths.settings: json_bytes(settings)}
            if original is not None or enabled:
                changes[self.paths.config] = render(original, settings["profiles"], adapter, dll)
            self.store.apply(changes, expected={self.paths.settings: previous, self.paths.config: original})
        return profile

    def import_profiles(self):
        """Импорт только в выключенные настройки, без смены владения чужим TOML."""
        with self.store.lock():
            original = read_bytes(self.paths.safe(self.paths.settings))
            settings = self.settings()
            document = parse_config(read_bytes(self.paths.safe(self.paths.config)))
            games = Steam(self.paths.home).games()
            imported = 0
            for profile in document.get("profile", []):
                if str(profile.get("name", "")).startswith(PREFIX):
                    continue
                candidates = targets(profile)
                # Не угадываем связь игры с EXE: импорт возможен по точному имени профиля.
                game = next((g for g in games if g["name"] == profile.get("name")), None)
                if not game or game["appid"] in settings["profiles"] or len(candidates) != 1:
                    continue
                value = {key: profile[key] for key in ("multiplier", "flow_scale", "performance_mode") if key in profile}
                settings["profiles"][game["appid"]] = validate_profile(
                    game["appid"], {**value, "process": candidates[0], "enabled": False,
                                    "runtime": settings.get("active_runtime") or "historical"})
                imported += 1
            self.store.apply({self.paths.settings: json_bytes(settings)},
                             expected={self.paths.settings: original}, kind="profile-import")
            return imported

    def activate(self, slot):
        with self.store.lock():
            self.assert_config_access()
            original = read_bytes(self.paths.safe(self.paths.settings))
            settings = self.settings()
            if any(p["enabled"] for p in settings["profiles"].values()):
                raise ThorError("Перед сменой runtime выключите профили и завершите игру")
            payload = self.runtimes.activation(slot)
            settings["active_runtime"] = slot
            self.store.apply({self.paths.manifest: payload, self.paths.settings: json_bytes(settings)},
                             expected={self.paths.settings: original}, kind="runtime-activate")
        return slot

    def rollback(self):
        self.assert_config_access()
        return self.store.rollback()

    def uninstall_runtime(self):
        with self.store.lock():
            self.assert_config_access()
            settings = self.settings()
            raw = read_bytes(self.paths.safe(self.paths.config))
            active = self.runtimes.active()
            for profile in settings["profiles"].values():
                profile["enabled"] = False
            settings["active_runtime"] = None
            changes = {self.paths.settings: json_bytes(settings), self.paths.manifest: None}
            if raw is not None:
                changes[self.paths.config] = render(raw, settings["profiles"],
                                                   active["adapter"] if active else "historical-2dev")
            self.store.apply(changes, kind="runtime-disable")
        # Слоты и история остаются для восстановления, автоматического rmtree нет.

    def probe_vulkan(self):
        try:
            mode = "loader" if DeviceProbe(self.paths).scan()["native_runtime"] else "summary"
            result = self.device_probe(mode)
            return {"available": True, "listed": result["layer_discovered"], "gpu": result["gpu"],
                    "driver": result["driver"], "exit_code": result["exit_code"]}
        except (OSError, ThorError, subprocess.SubprocessError) as exc:
            self._last_device_probe = {"mode": "loader", "error": str(exc), "fg_actually_verified": False}
            return {"available": shutil.which("vulkaninfo") is not None, "listed": None, "gpu": None, "driver": None}

    def device_probe(self, mode="check"):
        probe = DeviceProbe(self.paths)
        if mode not in ("check", "host-load", "summary", "loader"):
            raise ThorError("Этот режим доступен только через CLI с явным запуском")
        if mode == "check":
            return probe.scan()
        result = probe.run(mode)
        previous = getattr(self, "_last_device_probe", {})
        if previous.get("library_sha256") != result.get("library_sha256"):
            previous = {}
        # Разные проверки одного SHA дополняют друг друга, а не стирают host-load.
        merged = {**previous, **{key: value for key, value in result.items() if value is not None}}
        self._last_device_probe = merged
        return merged

    def processes(self):
        """Не передаём cmdline, environment и полный maps через RPC."""
        results = []
        if platform.system() != "Linux":
            return results
        for directory in Path("/proc").iterdir():
            if not directory.name.isdecimal():
                continue
            try:
                if directory.stat().st_uid != os.getuid():
                    continue
                with (directory / "maps").open(errors="replace") as stream:
                    maps = stream.read(2_000_000)
                exe_names = sorted(set(Path(line.split("/", 1)[-1]).name for line in maps.splitlines()
                                       if "/" in line and line.endswith(".exe")))
                loaded = "liblsfg-vk-layer.so" in maps
                if exe_names or loaded:
                    results.append({"pid": int(directory.name), "executables": exe_names[:12],
                                    "layer_mapped": loaded})
                if len(results) >= 100:
                    break
            except (OSError, ProcessLookupError):
                continue
        return results

    def status(self, probe=False):
        checks = []
        def check(key, ok, message):
            checks.append({"id": key, "state": "unknown" if ok is None else "ok" if ok else "error",
                           "message": message})
        host = platform.machine().lower()
        check("architecture", platform.system() == "Linux" and host in ("aarch64", "arm64"),
              "Среда: " + platform.system() + "/" + host)
        try:
            osrelease = Path("/etc/os-release").read_text("utf-8")
        except OSError:
            osrelease = ""
        check("armada", "armada" in osrelease.casefold() if osrelease else None,
              "ArmadaOS обнаружена" if "armada" in osrelease.casefold() else "ArmadaOS не подтверждена")
        active, settings = None, defaults()
        try:
            settings = self.settings()
            check("settings", True, "Настройки ThorFG прочитаны")
        except (OSError, ValueError, ThorError) as exc:
            check("settings", False, str(exc))
        try:
            active = self.runtimes.active()
            check("runtime", active is not None, "Файлы runtime, SHA-256 и ELF проверены" if active else "Runtime не активирован")
        except (OSError, ValueError, ThorError, TypeError) as exc:
            check("runtime", False, str(exc))
        configured = None
        try:
            raw = read_bytes(self.paths.safe(self.paths.config))
            document = parse_config(raw)
            validate_compatibility(document, active["adapter"] if active else "historical-2dev")
            configured = document.get("global", {}).get("dll")
            check("config", raw is not None, "TOML прочитан" if raw else "Конфигурация ещё не создана")
        except (OSError, ValueError, ThorError) as exc:
            check("config", False, str(exc))
        dll = Steam(self.paths.home).dll(bool(active and active["adapter"] == "stable-2.0"), configured)
        check("dll", dll is not None, "DLL обнаружена; совместимость проверяет runtime" if dll else "Подходящая DLL не найдена")
        managers = manager_conflicts(self.paths)
        conflicts, tools = layer_conflicts(self.paths)
        check("manager_conflict", not managers, "Другой менеджер: " + ", ".join(managers) if managers else "Другие менеджеры LSFG не обнаружены")
        check("layer_conflict", not conflicts, "Других LSFG manifest: " + str(len(conflicts)))
        check("tools", None if tools else True, "Других Vulkan-инструментов: " + str(len(tools)))
        check("transaction", not self.store.pending.exists(), "Есть незавершённая операция" if self.store.pending.exists() else "Нет незавершённых операций")
        overrides = any(os.environ.get(name) for name in ("LSFGVK_CONFIG", "LSFGVK_ENV", "LSFGVK_PROFILE", "DISABLE_LSFGVK"))
        check("overrides", not overrides, "Есть переменные LSFGVK/DISABLE_LSFGVK, влияющие на применение" if overrides else "Переопределения в окружении backend не обнаружены; окружение игры проверьте отдельно")
        games = self.games()
        check("games", bool(games["games"]), "Steam-игры обнаружены" if games["games"] else "Установленные Steam-игры не найдены")
        check("backend", True, "Decky backend ответил")
        vulkan = self.probe_vulkan() if probe else {"available": None, "listed": None, "gpu": None, "driver": None}
        check("loader", vulkan["listed"], "Слой перечислен loader" if vulkan["listed"] else "Обнаружение loader не подтверждено")
        lifecycle = self.device_probe()
        lifecycle["runtime_activated"] = active is not None
        reasons = lifecycle["write_block_reasons"][:]
        if active is None:
            reasons.append("Runtime ThorFG не активирован")
        if platform.system() != "Linux" or host not in ("aarch64", "arm64"):
            reasons.append("Применение профилей требует Linux ARM64")
        lifecycle["profiles_writable"] = not reasons
        lifecycle["profile_write_block_reasons"] = reasons
        lifecycle["activation_allowed"] = not lifecycle["read_only"] and host in ("aarch64", "arm64") and platform.system() == "Linux" and not any(p["enabled"] for p in settings["profiles"].values())
        last_probe = getattr(self, "_last_device_probe", None)
        if last_probe and last_probe.get("library_sha256") and (not lifecycle["native_runtime"] or last_probe["library_sha256"] != lifecycle["native_runtime"].get("sha256")):
            last_probe = None
        lifecycle["last_probe"] = last_probe
        return {"stage": "Configuration Verified" if active and all(c["state"] != "error" for c in checks) else "Требуется проверка",
                "hardware_verified": False, "host_architecture": host,
                "runtime": {key: active[key] for key in ("slot", "version", "architecture", "adapter", "commit")} if active else None,
                "checks": checks, "vulkan": vulkan, "dll_found": dll is not None,
                "game_count": len(games["games"]), "profile_count": len(settings["profiles"]),
                "settings": settings, "runtimes": self.runtimes.list(), "warnings": games["warnings"],
                "lifecycle": lifecycle}

    def export(self):
        status = self.status(probe=False)
        # Только фиксированная схема. Исключены сообщения ошибок с путями, имена игр,
        # процессы, конфигурация, GPU-строки сторонних инструментов и окружение.
        report = {"thorfg": "0.1.0-dev", "hardware_verified": False,
                  "host_architecture": status["host_architecture"],
                  "runtime": status["runtime"], "dll_found": status["dll_found"],
                  "game_count": status["game_count"], "profile_count": status["profile_count"],
                  "checks": [{"id": item["id"], "state": item["state"]} for item in status["checks"]],
                  "loader_listed": status["vulkan"]["listed"]}
        # Имена слотов — пользовательские: также не экспортируем.
        if report["runtime"]:
            report["runtime"].pop("slot", None)
        observed = status["lifecycle"]["last_probe"] or {}
        report["probe_evidence"] = {key: observed.get(key) if isinstance(observed.get(key), bool) else None
                                    for key in ("host_load_verified", "layer_discovered", "layer_inserted",
                                                "runtime_initialized", "swapchain_query_warning", "timed_out")}
        report["probe_evidence"]["fg_actually_verified"] = False
        report["loader_listed"] = report["probe_evidence"]["layer_discovered"]
        path = self.paths.safe(self.paths.state / "reports/diagnostic.txt")
        atomic(path, json_bytes(report), self.paths)
        return str(path)
