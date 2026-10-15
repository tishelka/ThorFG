import json
from pathlib import Path
import shutil

from .paths import Paths, ThorError
from .storage import Store, json_bytes, read_bytes
from .bundle import (SOURCES, LAYER, LIBRARY, MANIFEST, SLOT, sha256, inspect_bundle, verify_sums)
from .elf import elf, elf_info


def layer_conflicts(paths: Paths):
    roots = [paths.config_root / "vulkan", paths.data_root / "vulkan", paths.home / ".local/share/vulkan",
             Path("/etc/vulkan"), Path("/usr/share/vulkan"), Path("/usr/local/share/vulkan")]
    conflicts, tools = [], []
    seen = set()
    for root in roots:
        for directory in ("implicit_layer.d", "explicit_layer.d"):
            for path in (root / directory).glob("*.json"):
                if path in seen or path == paths.manifest:
                    continue
                seen.add(path)
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    text = path.read_text("utf-8")
                    if "lsfg" in (path.name + text).casefold():
                        conflicts.append(str(path))
                    if any(word in (path.name + text).casefold() for word in ("mako", "mangohud", "vkbasalt")):
                        tools.append(str(path))
                except (OSError, UnicodeError):
                    continue
    return conflicts, tools


def manager_conflicts(paths: Paths):
    found = []
    if (paths.config_root / "armada-lsfg-manager").exists():
        found.append("ArmadaLSFG settings")
    roots = [paths.decky_root / "plugins", Path("/usr/share/decky-plugins")]
    for root in roots:
        for metadata in root.glob("*/plugin.json"):
            try:
                if metadata.stat().st_size > 100_000:
                    continue
                name = json.loads(metadata.read_text("utf-8")).get("name", "")
                if "lsfg" in name.casefold() and name != "ThorFG":
                    found.append(name[:80])
            except (OSError, ValueError, TypeError):
                continue
    return sorted(set(found))


class Runtimes:
    def __init__(self, paths: Paths):
        self.paths = paths

    def slot(self, name):
        if not isinstance(name, str) or not SLOT.fullmatch(name):
            raise ThorError("Неверное имя слота runtime")
        return self.paths.safe(self.paths.runtimes / name)

    def list(self):
        result = []
        self.paths.safe(self.paths.runtimes)
        for directory in sorted(self.paths.runtimes.glob("*")):
            try:
                self.slot(directory.name)
                report, _ = inspect_bundle(directory)
                result.append({"slot": directory.name, "version": report["version"],
                               "architecture": "aarch64", "adapter": report["adapter"],
                               "commit": report["commit"], "integrity": True})
            except (OSError, ValueError, ThorError, TypeError):
                result.append({"slot": directory.name, "integrity": False})
        return result

    def active(self):
        self.paths.safe(self.paths.manifest)
        if not self.paths.manifest.is_file():
            return None
        data = json.loads(self.paths.manifest.read_text("utf-8"))
        lib = Path(data.get("layer", {}).get("library_path", ""))
        self.paths.safe(lib)
        if lib.name != LIBRARY or lib.parent.parent != self.paths.runtimes:
            raise ThorError("ThorFG manifest ссылается на чужую библиотеку")
        report, manifest = inspect_bundle(self.slot(lib.parent.name))
        expected = dict(manifest)
        expected["layer"] = {**manifest["layer"], "library_path": str(lib)}
        if data != expected:
            raise ThorError("Установленный manifest изменён извне")
        return {"slot": lib.parent.name, **report}

    def import_bundle(self, directory: Path, name: str):
        directory = directory.resolve()
        bundle_report, _ = inspect_bundle(directory)
        destination = self.slot(name)
        if destination.exists():
            raise ThorError("Слот уже существует; выберите новое имя для обновления")
        if shutil.disk_usage(self.paths.home).free < 128 * 1024 * 1024:
            raise ThorError("Для установки требуется не менее 128 МиБ свободного места")
        # Снимок байтов повторно проверяется до транзакции, чтобы копирование не приняло
        # изменившийся после inspect_bundle бинарник.
        names = {LIBRARY, MANIFEST, "UPSTREAM-LICENSE", "build-report.json"}
        if bundle_report.get("schema_version") == 2:
            names |= verify_sums(directory) | {"SHA256SUMS"}
        changes = {destination / file: (directory / file).read_bytes() for file in names}
        report = json.loads(changes[destination / "build-report.json"])
        if report != bundle_report:
            raise ThorError("Build-report изменился во время чтения")
        for file in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE"):
            if sha256(changes[destination / file]) != report["sha256"][file]:
                raise ThorError("Артефакты изменились во время чтения")
        if report.get("schema_version") == 2:
            for line in changes[destination / "SHA256SUMS"].decode("utf-8").splitlines():
                digest, name = line.split("  ", 1)
                if destination / name not in changes or sha256(changes[destination / name]) != digest:
                    raise ThorError("SHA256SUMS изменился во время чтения")
        with Store(self.paths).lock():
            if destination.exists():
                raise ThorError("Слот уже создан другим процессом")
            Store(self.paths).apply(changes, kind="runtime-import")
        return name

    def activation(self, name):
        conflicts, _ = layer_conflicts(self.paths)
        if conflicts:
            raise ThorError("Обнаружена другая установка LSFG-VK; автоматическая активация остановлена")
        if manager_conflicts(self.paths):
            raise ThorError("Обнаружен другой менеджер LSFG; разрешите конфликт по инструкции")
        directory = self.slot(name)
        _, manifest = inspect_bundle(directory)
        if self.paths.manifest.exists():
            self.active()  # Не перезаписывать файл, которым ThorFG не владеет.
        manifest["layer"]["library_path"] = str(directory / LIBRARY)
        return json_bytes(manifest)
