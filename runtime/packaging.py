"""Упаковка проверенной уже существующей сборки, без configure/build/download."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from thorfg.bundle import (LIBRARY, MANIFEST, SOURCES, inspect_bundle, sha256, validate_manifest)
from thorfg.elf import elf, elf_info
from thorfg.paths import ThorError, guarded
from .source import verify_checkout
from .toolchain import output, validate_cache


def package_existing(root, checkout, build, destination, source, tools, expected_sha=None, mode="recovered"):
    checkout, build = checkout.resolve(), build.resolve()
    destination = guarded(destination, root)
    if destination.exists():
        raise ThorError("Каталог артефактов уже существует; выберите новый --output. Файлы не перезаписаны")
    verified = verify_checkout(checkout, source, build)
    evidence = validate_cache(checkout, build, completed=True)
    library = build / "lsfg-vk-layer" / LIBRARY
    manifest_path = build / "lsfg-vk-layer" / MANIFEST
    for path in (library, manifest_path):
        if path.is_symlink() or not path.is_file():
            raise ThorError("Существующий результат отсутствует или является ссылкой")
    elf(library)
    manifest = json.loads(manifest_path.read_text("utf-8"))
    validate_manifest(manifest, SOURCES[source["commit"]])
    digest = sha256(library.read_bytes())
    record_path = build / "thorfg-build.json"
    if expected_sha is None:
        if not record_path.is_file():
            raise ThorError("Нет ThorFG build record: для ручной сборки нужен --expected-sha256 из вашего протокола")
        record = json.loads(record_path.read_text("utf-8"))
        if record.get("commit") != source["commit"] or record.get("source_tree") != source["tree"]:
            raise ThorError("Build record не соответствует checkout")
        expected_sha = record.get("library_sha256")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha) or digest != expected_sha:
        raise ThorError("SHA-256 существующей библиотеки не совпал с явно подтверждённым результатом")
    evidence.update({"mode": mode, "binary_sha256_confirmed": digest,
                     "binding": "operator SHA-256 or local ThorFG build record + CMake/Ninja metadata",
                     "limitation": "Local metadata is evidence, not a cryptographic attestation of compiler execution"})
    report = {**source, **verified, "schema_version": 2, "architecture": "aarch64", "patches": [],
              "hardware_verified": False, "build_evidence": evidence,
              "tools_observed_at_packaging": {key: output(tools[name], "--version")
                   for key, name in (("clang", "clang++"), ("llvm", "llvm-ar"), ("cmake", "cmake"))},
              "readelf_header": output(tools["readelf"], "-h", library),
              "readelf_dynamic": output(tools["readelf"], "-d", library),
              "readelf_versions": output(tools["readelf"], "--version-info", library),
              "dynamic_symbols": output(tools["nm"], "-D", library)}
    if "vkNegotiateLoaderLayerInterfaceVersion" not in report["dynamic_symbols"]:
        raise ThorError("Отсутствует экспорт Vulkan loader negotiation")
    license_path = checkout / ("LICENSE.md" if source["adapter"] == "historical-2dev" else "LICENSE.txt")
    files = {LIBRARY: library, MANIFEST: manifest_path, "UPSTREAM-LICENSE": license_path}
    cli = build / "lsfg-vk-cli/lsfg-vk-cli"
    if cli.is_file():
        info = elf_info(cli)
        if not (info["architecture"] == "aarch64" and info["bits"] == 64 and info["header_complete"]
                and info["little_endian"] and info["version"] == 1):
            raise ThorError("CLI не является AArch64")
        files["lsfg-vk-cli"] = cli
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Staging создаётся рядом с назначением. Ничего в checkout/build не меняется.
    with tempfile.TemporaryDirectory(prefix=".thorfg-package-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        for name, path in files.items():
            if path.is_symlink():
                raise ThorError("Ссылки не включаются в runtime-пакет")
            shutil.copy2(path, stage / name)
        if sha256((stage / LIBRARY).read_bytes()) != digest:
            raise ThorError("Библиотека изменилась во время упаковки")
        report["sha256"] = {name: sha256((stage / name).read_bytes()) for name in files}
        (stage / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sums = {**report["sha256"], "build-report.json": sha256((stage / "build-report.json").read_bytes())}
        (stage / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items())), encoding="utf-8")
        verify_checkout(checkout, source, build)
        inspect_bundle(stage)
        if destination.exists():
            raise ThorError("Каталог назначения появился во время упаковки")
        # Публикуем готовый каталог одним rename; старые артефакты не удаляются.
        stage.rename(destination)
    return report
