#!/usr/bin/env python3
"""Пользовательский установщик и диагностика. Запускайте из корня исходников."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import sys

sys.dont_write_bytecode = True  # check/dry-run/diagnose не записывают import cache в HOME.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/py_modules"))
sys.path.insert(0, str(ROOT / "plugin/backend"))

from thorfg.paths import Paths, ThorError
from thorfg.runtime import inspect_bundle
from thorfg.service import Service


def main():
    parser = argparse.ArgumentParser(description="ThorFG: установка в домашний каталог без root")
    parser.add_argument("mode", choices=["check", "dry-run", "install", "update", "activate",
                                         "rollback", "uninstall", "diagnose"])
    parser.add_argument("--bundle", type=Path, help="Каталог проверяемой локальной ARM64-сборки")
    parser.add_argument("--slot", default="historical", help="Имя слота runtime")
    parser.add_argument("--export", action="store_true", help="Сохранить обезличенный отчёт")
    parser.add_argument("--probe-vulkan", action="store_true", help="Явный изолированный Vulkan-тест только с diagnose")
    args = parser.parse_args()
    paths = Paths.environment()
    service = Service(paths)
    try:
        if args.mode in ("check", "diagnose"):
            print(json.dumps(service.status(probe=args.mode == "diagnose" and args.probe_vulkan), ensure_ascii=False, indent=2))
            if args.export:
                print("Обезличенный отчёт:", service.export())
            return 0
        if args.mode == "rollback":
            print("Восстановлена операция:", service.rollback())
            return 0
        if args.mode == "dry-run":
            if args.bundle:
                inspect_bundle(args.bundle.resolve())
                print("Проверены ELF, provenance и контрольные суммы")
            print("Система:", platform.system(), platform.machine())
            print("Свободно МиБ:", shutil.disk_usage(paths.home).free // 1024**2)
            print("Изменения при установке:", service.runtimes.slot(args.slot))
            print("Активация отдельной командой изменит:", paths.manifest, paths.settings)
            print("Существующие файлы не изменены")
            return 0
        if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
            raise ThorError("Установка runtime предназначена для Linux ARM64")
        if args.mode in ("install", "update"):
            if args.bundle is None:
                raise ThorError("Укажите --bundle с результатом локальной сборки")
            print("Установлен слот:", service.runtimes.import_bundle(args.bundle, args.slot))
            print("Для активации завершите игры и выполните: python3 scripts/thorfg.py activate --slot", args.slot)
        elif args.mode == "activate":
            print("Активирован слот:", service.activate(args.slot))
        elif args.mode == "uninstall":
            service.uninstall_runtime()
            print("Собственный manifest удалён, профили выключены. Слоты и история сохранены для восстановления.")
        return 0
    except (ThorError, OSError, ValueError, TypeError) as exc:
        print("Ошибка ThorFG:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
