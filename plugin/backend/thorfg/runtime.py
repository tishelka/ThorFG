import hashlib
import json
from pathlib import Path
import shutil
import struct

from .config import SLOT
from .paths import Paths, ThorError
from .storage import Store, json_bytes, read_bytes


SOURCES = {
    "8b0da2661c6f3473a7fccc8ba643880050e71642": ("historical-2dev", "v2.0.0-dev", "1.4.328"),
    "2333707d55b68ddd8066fd95404c3b7d07e00d3a": ("stable-2.0", "2.0.0", "1.4.350"),
}
LAYER = "VK_LAYER_LSFGVK_frame_generation"
LIBRARY = "liblsfg-vk-layer.so"
MANIFEST = "VkLayer_LSFGVK_frame_generation.json"


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def elf(path: Path):
    with path.open("rb") as stream:
        header = stream.read(64)
    if len(header) < 64 or header[:4] != b"\x7fELF" or header[4] != 2 or header[5] != 1 or header[6] != 1:
        raise ThorError("Требуется ELF64 little-endian shared object")
    kind, machine = struct.unpack_from("<HH", header, 16)
    if kind != 3 or machine != 183:
        raise ThorError("Библиотека не является AArch64 ELF shared object")
    return "aarch64"


def inspect_bundle(directory: Path):
    for name in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE", "build-report.json"):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ThorError("Артефакт отсутствует или является ссылкой")
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ThorError("Артефакт превышает допустимый размер")
    report = json.loads((directory / "build-report.json").read_text("utf-8"))
    source = SOURCES.get(report.get("commit"))
    if source is None or report.get("adapter") != source[0] or report.get("version") != source[1]:
        raise ThorError("Неизвестная или несовместимая версия runtime")
    if report.get("architecture") != "aarch64" or report.get("patches") != []:
        raise ThorError("Не поддерживаются патчи или неверная архитектура runtime")
    for name in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE"):
        if sha256((directory / name).read_bytes()) != report.get("sha256", {}).get(name):
            raise ThorError("Контрольная сумма артефакта не совпадает")
    elf(directory / LIBRARY)
    manifest = json.loads((directory / MANIFEST).read_text("utf-8"))
    layer = manifest.get("layer", {})
    if layer.get("name") != LAYER or layer.get("type") != "GLOBAL" or layer.get("api_version") != source[2]:
        raise ThorError("Неверный Vulkan manifest")
    if layer.get("disable_environment") != {"DISABLE_LSFGVK": "1"}:
        raise ThorError("Manifest не поддерживает безопасное отключение")
    return report, manifest


def layer_conflicts(paths: Paths):
    roots = [paths.data_root / "vulkan", paths.home / ".local/share/vulkan",
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
        inspect_bundle(directory)
        destination = self.slot(name)
        if destination.exists():
            raise ThorError("Слот уже существует; выберите новое имя для обновления")
        if shutil.disk_usage(self.paths.home).free < 128 * 1024 * 1024:
            raise ThorError("Для установки требуется не менее 128 МиБ свободного места")
        # Снимок байтов повторно проверяется до транзакции, чтобы копирование не приняло
        # изменившийся после inspect_bundle бинарник.
        changes = {destination / file: (directory / file).read_bytes()
                   for file in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE", "build-report.json")}
        report = json.loads(changes[destination / "build-report.json"])
        for file in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE"):
            if sha256(changes[destination / file]) != report["sha256"][file]:
                raise ThorError("Артефакты изменились во время чтения")
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
