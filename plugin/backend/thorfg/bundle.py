"""Проверка локального runtime-пакета; доступна сборщику без tomlkit."""
import hashlib
import json
from pathlib import Path
import re

from .elf import elf
from .paths import ThorError

SOURCES = {
    "8b0da2661c6f3473a7fccc8ba643880050e71642": ("historical-2dev", "v2.0.0-dev", "1.4.328"),
    "2333707d55b68ddd8066fd95404c3b7d07e00d3a": ("stable-2.0", "2.0.0", "1.4.350"),
}
TREES = {
    "8b0da2661c6f3473a7fccc8ba643880050e71642": "8e35469d1977b8640b44bb88f122a53f7f21eb41",
    "2333707d55b68ddd8066fd95404c3b7d07e00d3a": "94f6e867400fca39e61bd0fefef83ff65aaac24d",
}
REPOSITORIES = {
    "historical-2dev": {"https://git.lsfg-vk.dev/lsfg-vk-archive.git",
                        "https://github.com/eugeniosegala/lsfg-vk-experimental.git"},
    "stable-2.0": {"https://git.lsfg-vk.dev/lsfg-vk.git"},
}
LAYER = "VK_LAYER_LSFGVK_frame_generation"
LIBRARY = "liblsfg-vk-layer.so"
MANIFEST = "VkLayer_LSFGVK_frame_generation.json"
SLOT = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def validate_manifest(manifest, source):
    layer = manifest.get("layer", {})
    if layer.get("name") != LAYER or layer.get("type") != "GLOBAL" or layer.get("api_version") != source[2]:
        raise ThorError("Неверный Vulkan manifest")
    if layer.get("disable_environment") != {"DISABLE_LSFGVK": "1"}:
        raise ThorError("Manifest не поддерживает безопасное отключение")


def verify_sums(directory):
    path = directory / "SHA256SUMS"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
        raise ThorError("Отсутствует корректный SHA256SUMS")
    found = set()
    for line in path.read_text("utf-8").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in found or match[2] in (".", "..", "SHA256SUMS"):
            raise ThorError("Некорректная запись SHA256SUMS")
        name = match[2]
        if name not in {LIBRARY, MANIFEST, "UPSTREAM-LICENSE", "build-report.json", "lsfg-vk-cli"}:
            raise ThorError("Неожиданный файл в runtime-пакете")
        candidate = directory / name
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 64 * 1024**2:
            raise ThorError("Небезопасный файл в SHA256SUMS")
        if sha256(candidate.read_bytes()) != match[1]:
            raise ThorError("SHA256SUMS: контрольная сумма не совпадает")
        found.add(name)
    if not {LIBRARY, MANIFEST, "UPSTREAM-LICENSE", "build-report.json"} <= found:
        raise ThorError("SHA256SUMS не покрывает обязательные файлы")
    return found


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
    validate_manifest(manifest, source)
    if report.get("schema_version", 1) == 2:
        if report.get("source_tree") != TREES[report["commit"]] or report.get("source_repository") not in REPOSITORIES[source[0]]:
            raise ThorError("Недостоверный source provenance")
        if report.get("hardware_verified") is not False or not isinstance(report.get("build_evidence"), dict):
            raise ThorError("Некорректные данные проверки runtime")
        verify_sums(directory)
    elif report.get("schema_version", 1) != 1:
        raise ThorError("Неизвестная схема build-report")
    return report, manifest
