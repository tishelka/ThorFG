"""По умолчанию — только чтение. Активные тесты изолированы и ограничены временем."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from .bundle import LIBRARY, MANIFEST, LAYER, SOURCES, inspect_bundle, sha256, validate_manifest
from .elf import elf, elf_info
from .paths import Paths, ThorError
from .runtime import Runtimes, layer_conflicts, manager_conflicts
from .steam import Steam


def manifest_library(manifest_path, data):
    value = data.get("layer", {}).get("library_path")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if "/" in value or "\\" in value:
        return manifest_path.parent / path
    return None  # Bare soname: не угадываем поиск динамического загрузчика.


def external_layers(paths):
    conflicts, tools = layer_conflicts(paths)
    result = []
    for filename in conflicts:
        path = Path(filename)
        item = {"manifest": filename, "architecture": "unknown", "library": None, "name": None}
        try:
            data = json.loads(path.read_text("utf-8"))
            item["name"] = data.get("layer", {}).get("name")
            library = manifest_library(path, data)
            if library:
                item["library"] = str(library)
                item["architecture"] = elf_info(library)["architecture"]
        except (OSError, ValueError, ThorError, TypeError):
            item["error"] = "Manifest или библиотека недоступны; файлы не изменялись"
        result.append(item)
    return result, tools


def analyze_vulkan(stdout, stderr, exit_code, *, timed_out=False, library_sha=None):
    text = stdout + "\n" + stderr
    instance = bool(re.search(r'Insert(?:ed)? instance layer\s+"' + LAYER + '"', text, re.I))
    device = bool(re.search(r'Insert(?:ed)? device layer\s+"' + LAYER + '"', text, re.I))
    def field(name):
        match = re.search(r"^\s*" + name + r"\s*=\s*(.+)$", stdout, re.M)
        return match[1][:160] if match else None
    swapchain_warning = "vkCreateSwapchainKHR" in text and ("failed" in text.casefold() or "error" in text.casefold())
    return {"mode": "vulkan", "exit_code": exit_code, "timed_out": timed_out,
            "library_sha256": library_sha, "gpu": field("deviceName"), "driver": field("driverName"),
            "layer_discovered": instance or device or bool(re.search(r"^\s*" + re.escape(LAYER) + r"(?:\s|:)", stdout, re.M)), "instance_layer_inserted": instance,
            "device_layer_inserted": device, "layer_inserted": instance and device,
            "profile_selected": "lsfg-vk: using profile with name" in text,
            "host_load_verified": None, "runtime_initialized": None, "fg_actually_verified": False,
            "swapchain_query_warning": swapchain_warning,
            "interpretation": "Ошибка запроса swapchain в vulkaninfo не доказывает несовместимость GPU" if swapchain_warning else
                              "Loader insertion и выбор профиля не подтверждают генерацию кадров",
            "observed_at": datetime.now(timezone.utc).isoformat()}


def isolated_environment(directory, manifest_dir, library=None, dll=None):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("VK_LAYER", "VK_ADD_", "VK_IMPLICIT_LAYER", "VK_INSTANCE_LAYERS", "VK_LOADER_LAYERS", "LSFGVK_"))
           and key not in ("DISABLE_LSFGVK", "LD_PRELOAD", "MANGOHUD", "ENABLE_VKBASALT")}
    env.update({"VK_IMPLICIT_LAYER_PATH": str(manifest_dir), "VK_LAYER_PATH": str(directory / "explicit"),
                "XDG_CONFIG_HOME": str(directory / "config"), "XDG_DATA_HOME": str(directory / "data"),
                "XDG_CACHE_HOME": str(directory / "cache"), "MESA_SHADER_CACHE_DIR": str(directory / "cache/mesa"),
                "LSFGVK_CONFIG": str(directory / "config/lsfg-vk/conf.toml"), "VK_LOADER_DEBUG": "layer,error"})
    if library is not None:
        env.update({"LSFGVK_ENV": "1", "LSFGVK_MULTIPLIER": "2", "LSFGVK_FLOW_SCALE": "0.5",
                    "LSFGVK_PERFORMANCE_MODE": "1"})
        if dll:
            env["LSFGVK_DLL_PATH"] = dll
    else:
        env["DISABLE_LSFGVK"] = "1"
    return env


class DeviceProbe:
    def __init__(self, paths: Paths, project=None):
        self.paths = paths
        self.project = Path(project) if project else paths.home / "thorfg"

    def candidates(self):
        candidates = []
        roots = [(self.project / ".build/historical/build-llvm/lsfg-vk-layer", "build"),
                 (self.project / ".build/historical/build/lsfg-vk-layer", "build"),
                 (self.project / ".build/stable/build-llvm/lsfg-vk-layer", "build")]
        roots += [(path, "bundle") for path in sorted((self.project / "artifacts/runtime").glob("*"))]
        roots += [(path, "slot") for path in sorted(self.paths.runtimes.glob("*"))]
        for directory, kind in roots:
            path = directory / LIBRARY
            if not path.is_file():
                continue
            item = {"library": str(path), "kind": kind, "elf_verified": False,
                    "architecture": "unknown", "bundle_verified": False}
            try:
                if path.stat().st_size > 64 * 1024**2:
                    raise ThorError("Библиотека слишком большая")
                item.update(elf_info(path))
                item["sha256"] = sha256(path.read_bytes())
                item["elf_verified"] = elf(path) == "aarch64"
                item["manifest_found"] = (directory / MANIFEST).is_file()
                if kind != "build":
                    report, _ = inspect_bundle(directory)
                    item.update({"bundle_verified": True, "version": report["version"]})
            except (OSError, ValueError, ThorError, TypeError) as exc:
                item["error"] = str(exc)
            candidates.append(item)
        return candidates

    def scan(self, library=None):
        candidates = self.candidates()
        if library:
            path = Path(library)
            if path.stat().st_size > 64 * 1024**2:
                raise ThorError("Библиотека слишком большая")
            info = elf_info(path)
            try:
                verified = elf(path) == "aarch64"
            except ThorError:
                verified = False
            candidates.insert(0, {"library": str(path), "kind": "explicit", **info,
                                  "sha256": sha256(path.read_bytes()),
                                  "elf_verified": verified,
                                  "bundle_verified": False, "manifest_found": (path.parent / MANIFEST).is_file()})
        layers, tools = external_layers(self.paths)
        managers = manager_conflicts(self.paths)
        reasons = []
        if managers:
            reasons.append("Обнаружены сторонние менеджеры LSFG: " + ", ".join(managers))
        if layers:
            reasons.append("Обнаружены сторонние Vulkan LSFG manifest: " + str(len(layers)))
        if any(os.environ.get(key) for key in ("LSFGVK_CONFIG", "LSFGVK_ENV", "LSFGVK_PROFILE", "DISABLE_LSFGVK")):
            reasons.append("Окружение переопределяет LSFG-VK")
        active, activation_error = None, None
        try:
            active = Runtimes(self.paths).active()
        except (OSError, ValueError, ThorError, TypeError) as exc:
            activation_error = str(exc)
        eligible = [item for item in candidates if item["elf_verified"] and
                    (item["kind"] in ("build", "explicit") or item["bundle_verified"])]
        if library:
            native = candidates[0] if candidates[0] in eligible else None
        elif active:
            active_library = str(self.paths.runtimes / active["slot"] / LIBRARY)
            native = next((item for item in eligible if item["library"] == active_library), None)
        else:
            native = next(iter(eligible), None)
        return {"candidates": candidates, "native_runtime": native, "external_layers": layers,
                "external_managers": managers, "other_vulkan_tools": tools,
                "read_only": bool(reasons), "write_block_reasons": reasons,
                "runtime_activated": active is not None, "activation_error": activation_error,
                "slot_installed": any(item["kind"] == "slot" and item["bundle_verified"] for item in candidates),
                "local_build_found": any(item["kind"] == "build" and item["elf_verified"] for item in candidates),
                "local_bundle_found": any(item["kind"] == "bundle" and item["bundle_verified"] for item in candidates),
                "loader_tool_available": shutil.which("vulkaninfo") is not None,
                "evidence": {"elf_verified": bool(native), "host_load_verified": None,
                             "layer_discovered": None, "layer_inserted": None, "runtime_initialized": None,
                             "fg_actually_verified": False}, "hardware_verified": False}

    def run(self, mode, *, library=None, expected_sha=None, timeout=15, wayland_display=None):
        if mode == "check":
            result = self.scan(library)
            if expected_sha and (not result["native_runtime"] or result["native_runtime"]["sha256"] != expected_sha):
                raise ThorError("SHA-256 библиотеки не совпадает с ожидаемым")
            return result
        if mode not in ("host-load", "summary", "loader", "cube"):
            raise ThorError("Неизвестный режим диагностики")
        if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64") or os.geteuid() == 0:
            raise ThorError("Активные тесты выполняются обычным пользователем Linux ARM64")
        if not 1 <= timeout <= 60:
            raise ThorError("Тайм-аут должен быть от 1 до 60 секунд")
        scan = self.scan(library)
        native = scan["native_runtime"]
        selected = Path(native["library"]) if native else None
        if mode != "summary":
            if selected is None:
                raise ThorError("Нативная ARM64-библиотека не найдена")
            self.paths.safe(selected)
            elf(selected)
            if expected_sha and native["sha256"] != expected_sha:
                raise ThorError("SHA-256 библиотеки не совпадает с ожидаемым")
        executable = shutil.which("vkcube" if mode == "cube" else "vulkaninfo") if mode != "host-load" else None
        if mode != "host-load" and not executable:
            raise ThorError("Не найден локальный " + ("vkcube" if mode == "cube" else "vulkaninfo"))
        parent = self.paths.safe(self.paths.data_root / "thorfg/probes")
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="probe-", dir=parent) as temporary:
            directory = Path(temporary)
            manifests = directory / "implicit_layer.d"
            manifests.mkdir()
            (directory / "explicit").mkdir()
            (directory / "config/lsfg-vk").mkdir(parents=True)
            (directory / "data").mkdir()
            (directory / "cache").mkdir()
            (directory / "config/lsfg-vk/conf.toml").write_text("version = 2\nprofile = []\n[global]\n", encoding="utf-8")
            if mode == "host-load":
                code = "import ctypes,os,sys; ctypes.CDLL(sys.argv[1], mode=os.RTLD_NOW|os.RTLD_LOCAL); print('THORFG_HOST_LOAD_OK')"
                env = isolated_environment(directory, manifests)
                try:
                    result = subprocess.run([sys.executable, "-c", code, str(selected)], capture_output=True,
                                            env=env, text=True, timeout=timeout, check=False)
                    ok = result.returncode == 0 and "THORFG_HOST_LOAD_OK" in result.stdout
                    return {"mode": mode, "host_load_verified": ok, "library_sha256": native["sha256"],
                            "exit_code": result.returncode, "runtime_initialized": None, "fg_actually_verified": False,
                            "error": None if ok else result.stderr[-2000:].replace(str(self.paths.home), "~")}
                except subprocess.TimeoutExpired:
                    return {"mode": mode, "library_sha256": native["sha256"], "host_load_verified": False,
                            "timed_out": True, "fg_actually_verified": False}
            dll = None
            if mode != "summary":
                manifest = json.loads((selected.parent / MANIFEST).read_text("utf-8"))
                source = next((item for item in SOURCES.values() if item[2] == manifest.get("layer", {}).get("api_version")), None)
                if source is None:
                    raise ThorError("Manifest имеет неизвестную версию")
                validate_manifest(manifest, source)
                manifest["layer"]["library_path"] = str(selected)
                (manifests / "ThorFG-test.json").write_text(json.dumps(manifest), encoding="utf-8")
                dll = Steam(self.paths.home).dll(source[0] == "stable-2.0")
                if mode == "cube" and dll is None:
                    raise ThorError("Для swapchain-теста нужна собственная подходящая DLL Lossless Scaling")
            env = isolated_environment(directory, manifests, selected if mode != "summary" else None, dll)
            args = [executable, "--summary"] if mode != "cube" else [executable, "--c", "120"]
            if mode == "cube":
                if wayland_display:
                    if "/" in wayland_display or ".." in wayland_display or not wayland_display.startswith("wayland-"):
                        raise ThorError("Укажите имя Wayland-сокета, например wayland-0")
                    env["WAYLAND_DISPLAY"] = wayland_display
                if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
                    runtime_dir = Path(env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
                    sockets = [p for p in runtime_dir.glob("wayland-*") if stat.S_ISSOCK(p.stat().st_mode) and p.stat().st_uid == os.getuid()]
                    if len(sockets) != 1:
                        raise ThorError("Нет однозначной графической сессии; укажите --wayland-display. Не запускайте vkcube из root")
                    env.update({"XDG_RUNTIME_DIR": str(runtime_dir), "WAYLAND_DISPLAY": sockets[0].name})
                if env.get("WAYLAND_DISPLAY"):
                    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
                    args += ["--wsi", "wayland"]
            timed_out = False
            try:
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout,
                                        encoding="utf-8", errors="replace", check=False)
                stdout, stderr, exit_code = result.stdout[:200_000], result.stderr[:200_000], result.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
                stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
                exit_code = None
            observed = analyze_vulkan(stdout, stderr, exit_code, timed_out=timed_out,
                                      library_sha=native["sha256"] if native else None)
            observed["mode"] = mode
            return observed
