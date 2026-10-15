#!/usr/bin/env python3
"""Сборка неизменённого закреплённого upstream на ARM64 в Fedora Distrobox."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False, env=None, cwd=None):
    return subprocess.run(list(map(str, args)), check=True, cwd=cwd, env=env,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description="Нативная ARM64-сборка LSFG-VK в Fedora Distrobox")
    parser.add_argument("--variant", choices=["historical", "stable"], default="historical")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
        raise SystemExit("Запустите этот скрипт на Thor в Linux ARM64; x86-сборка не заменяет AArch64")
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise SystemExit("Для исходников и сборки требуется не менее 2 ГиБ свободного места")
    sources = json.loads((ROOT / "runtime/sources.lock.json").read_text("utf-8"))
    source = sources[args.variant]
    output = args.output.resolve() / args.variant
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Каталог артефактов уже заполнен; укажите новый --output")
    if not args.inside:
        if not shutil.which("distrobox"):
            raise SystemExit("Distrobox не найден. Проверьте доступные средства ArmadaOS")
        name = "thorfg-build-f44"
        image = "registry.fedoraproject.org/fedora:44"
        containers = run("distrobox", "list", "--no-color", capture=True)
        names = [part.strip() for line in containers.splitlines() for part in line.split("|")[1:2]]
        if name not in names:
            run("distrobox", "create", "--yes", "--name", name, "--image", image)
        run("distrobox", "enter", "--name", name, "--", "python3", Path(__file__).resolve(),
            "--inside", "--variant", args.variant, "--output", args.output.resolve())
        return
    if not (Path("/run/.containerenv").exists() or Path("/.dockerenv").exists()):
        raise SystemExit("--inside допускается только внутри контейнера; host dnf не запускается")
    osrelease = Path("/etc/os-release").read_text()
    if 'ID=fedora' not in osrelease and 'ID="fedora"' not in osrelease:
        raise SystemExit("Ожидался Fedora-контейнер")
    run("sudo", "dnf", "install", "-y", "git", "cmake", "ninja-build", "clang", "lld",
        "vulkan-headers", "vulkan-loader-devel", "glslang", "pkgconf-pkg-config", "python3", "binutils", "file")
    work = ROOT / ".build" / args.variant
    if work.exists():
        raise SystemExit("Checkout уже существует; используйте чистую рабочую копию проекта")
    work.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", source["repository"], work)
    run("git", "checkout", "--detach", source["commit"], cwd=work)
    run("git", "submodule", "update", "--init", "--recursive", cwd=work)
    if run("git", "rev-parse", "HEAD", capture=True, cwd=work).strip() != source["commit"]:
        raise SystemExit("Не совпадает исходный SHA")
    if run("git", "status", "--porcelain", capture=True, cwd=work).strip():
        raise SystemExit("Исходники содержат незапланированные изменения")
    env = {**os.environ, "SOURCE_DATE_EPOCH": run("git", "show", "-s", "--format=%ct", capture=True, cwd=work).strip()}
    build = work / "build"
    run("cmake", "-S", work, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_CXX_COMPILER=clang++", "-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON",
        "-DLSFGVK_BUILD_UI=OFF", "-DLSFGVK_BUILD_CLI=ON", env=env)
    run("cmake", "--build", build, "--parallel", str(min(os.cpu_count() or 2, 4)), env=env)
    library = build / "lsfg-vk-layer/liblsfg-vk-layer.so"
    header = library.read_bytes()[:64]
    import struct
    if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<HH", header, 16) != (3, 183):
        raise SystemExit("Результат не является AArch64 ELF shared object")
    architecture = run("file", library, capture=True)
    elf_header = run("readelf", "-h", library, capture=True)
    dependencies = run("readelf", "-d", library, capture=True)
    output.mkdir(parents=True, exist_ok=True)
    manifest = build / "lsfg-vk-layer/VkLayer_LSFGVK_frame_generation.json"
    for path in (library, manifest):
        shutil.copy2(path, output / path.name)
    license_name = "LICENSE.md" if args.variant == "historical" else "LICENSE.txt"
    shutil.copy2(work / license_name, output / "UPSTREAM-LICENSE")
    cli = build / "lsfg-vk-cli/lsfg-vk-cli"
    if cli.is_file():
        shutil.copy2(cli, output / cli.name)
    report = {**source, "architecture": "aarch64", "patches": [], "hardware_verified": False,
              "compiler": run("clang++", "--version", capture=True),
              "cmake": run("cmake", "--version", capture=True), "os_release": osrelease,
              "container_image": "registry.fedoraproject.org/fedora:44",
              "packages": run("rpm", "-qa", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n", capture=True),
              "source_date_epoch": env["SOURCE_DATE_EPOCH"], "file": architecture,
              "readelf_header": elf_header, "readelf_dynamic": dependencies,
              "sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(output.iterdir()) if path.is_file()}}
    (output / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in report["sha256"].items()), encoding="utf-8")
    print("Сборка и ELF проверены:", output)
    print("Это не подтверждение загрузки слоя или Frame Generation на Thor Pro")


if __name__ == "__main__":
    main()
