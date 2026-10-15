#!/usr/bin/env python3
"""Нативная сборка или упаковка уже готового ARM64 LSFG-VK без потери build-llvm."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugin/backend"))

from thorfg.bundle import LIBRARY, sha256
from thorfg.paths import ThorError, guarded
from runtime.source import acquire, git, load_source, verify_checkout
from runtime.toolchain import cmake_arguments, discover_tools, validate_cache
from runtime.packaging import package_existing


def run(*args, capture=False, env=None):
    result = subprocess.run(list(map(str, args)), check=True, env=env, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout


def parser():
    cli = argparse.ArgumentParser(description="Сборка или восстановление ARM64 runtime ThorFG")
    cli.add_argument("--variant", choices=["historical", "stable"], default="historical")
    cli.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    cli.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime", help="Новый каталог, внутрь добавляется имя варианта")
    cli.add_argument("--use-existing-checkout", type=Path, help="Существующий checkout: без clone, fetch и checkout")
    cli.add_argument("--build-dir", type=Path, help="Существующий build-llvm либо новый build directory")
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--package-existing", action="store_true", help="Только проверить и упаковать существующую сборку; без компиляции и установки пакетов")
    mode.add_argument("--resume", action="store_true", help="Явно разрешить configure/build и обновление результата в выбранном build directory")
    cli.add_argument("--expected-sha256", help="SHA существующей ручной сборки из вашего протокола (не глобальный эталон)")
    cli.add_argument("--source", help="Предпочтительный URL из закреплённого списка источников")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
            raise ThorError("Запустите на Thor в Linux ARM64; успех x86-сборки не заменяет AArch64")
        source = load_source(ROOT, args.variant)
        destination = guarded(args.output.absolute() / args.variant, ROOT)
        if destination.exists():
            raise ThorError("Каталог артефактов уже существует; выберите новый --output")
        work = (args.use_existing_checkout or ROOT / ".build" / args.variant).absolute()
        build = (args.build_dir or work / "build-llvm").absolute()
        if ".." in work.parts or ".." in build.parts or work.is_symlink() or build.is_symlink():
            raise ThorError("Checkout/build не должны быть symlink или содержать ..")
        if args.package_existing:
            if not args.use_existing_checkout or not args.build_dir:
                raise ThorError("Для восстановления укажите --use-existing-checkout и --build-dir")
            tools = discover_tools()
            report = package_existing(ROOT, work, build, destination, source, tools, args.expected_sha256)
            print("Существующая сборка проверена и упакована без компиляции:", destination)
            print("SHA-256:", report["sha256"][LIBRARY])
            print("FG в игре не подтверждена; runtime не активирован")
            return 0
        if args.expected_sha256:
            raise ThorError("--expected-sha256 предназначен для --package-existing")
        if args.resume and not args.use_existing_checkout:
            raise ThorError("Для --resume явно укажите --use-existing-checkout")
        if work.exists() and not args.use_existing_checkout:
            raise ThorError("Checkout уже существует; выберите восстановление или явный --use-existing-checkout")
        if args.use_existing_checkout:
            verify_checkout(work, source, build)
        if build.exists():
            if not args.resume:
                raise ThorError("Build directory существует. --package-existing сохраняет результат; --resume явно разрешает пересборку")
            validate_cache(work, build)
        if not args.inside:
            if not shutil.which("distrobox"):
                raise ThorError("Distrobox не найден")
            name = "thorfg-build-f44"
            containers = run("distrobox", "list", "--no-color", capture=True)
            if name not in [part.strip() for line in containers.splitlines() for part in line.split("|")[1:2]]:
                run("distrobox", "create", "--yes", "--name", name, "--image", "registry.fedoraproject.org/fedora:44")
            forwarded = ["--variant", args.variant, "--output", str(args.output.absolute()), "--build-dir", str(build)]
            if args.use_existing_checkout:
                forwarded += ["--use-existing-checkout", str(work)]
            if args.resume:
                forwarded += ["--resume"]
            if args.source:
                forwarded += ["--source", args.source]
            run("distrobox", "enter", "--name", name, "--", "python3", Path(__file__).resolve(), "--inside", *forwarded)
            return 0
        if not (Path("/run/.containerenv").exists() or Path("/.dockerenv").exists()):
            raise ThorError("Установка build tools разрешена только внутри контейнера")
        osrelease = Path("/etc/os-release").read_text()
        if 'ID=fedora' not in osrelease and 'ID="fedora"' not in osrelease:
            raise ThorError("Ожидался Fedora-контейнер")
        if shutil.disk_usage(ROOT).free < 2 * 1024**3:
            raise ThorError("Для сборки требуется не менее 2 ГиБ свободного места")
        run("sudo", "dnf", "install", "-y", "git", "cmake", "ninja-build", "clang", "llvm", "lld",
            "vulkan-headers", "vulkan-loader-devel", "glslang", "pkgconf-pkg-config", "python3", "binutils", "file")
        tools = discover_tools()
        if not args.use_existing_checkout:
            work = acquire(ROOT, source, work, args.source)
        verified = verify_checkout(work, source, build)
        guarded(build, ROOT)
        epoch = git(work, "show", "-s", "--format=%ct")
        env = {**os.environ, "SOURCE_DATE_EPOCH": epoch}
        run(*cmake_arguments(work, build, tools), env=env)
        validate_cache(work, build)
        run(tools["cmake"], "--build", build, "--parallel", str(min(os.cpu_count() or 2, 4)), env=env)
        verify_checkout(work, source, build)
        record = {**verified, "library_sha256": sha256((build / "lsfg-vk-layer" / LIBRARY).read_bytes()),
                  "source_date_epoch": epoch, "hardware_verified": False}
        (build / "thorfg-build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        package_existing(ROOT, work, build, destination, source, tools, mode="resumed" if args.resume else "built")
        print("Сборка и ELF проверены:", destination)
        print("Это не подтверждение Frame Generation на Thor Pro")
        return 0
    except (ThorError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("Ошибка сборщика:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
