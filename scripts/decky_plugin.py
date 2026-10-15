#!/usr/bin/env python3
"""Установить только собственный Decky-пакет с проверкой путей и журналом."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/py_modules"))
sys.path.insert(0, str(ROOT / "plugin/backend"))
from thorfg.paths import Paths, ThorError
from thorfg.storage import Store, read_bytes


def deploy(paths, package=None, uninstall=False):
    target = paths.safe(paths.decky_root / "plugins/ThorFG")
    marker = target / "thorfg-package.json"
    previous = None
    snapshots = {marker: read_bytes(paths.safe(marker))}
    if target.exists():
        if not marker.is_file():
            raise ThorError("Каталог ThorFG существует без нашего manifest владения")
        paths.safe(marker)
        previous = json.loads(snapshots[marker])
        if previous.get("name") != "ThorFG":
            raise ThorError("Неизвестный владелец каталога плагина")
    changes = {}
    if previous:
        for name, checksum in previous["files"].items():
            path = paths.safe(target / name)
            if not path.is_relative_to(target):
                raise ThorError("Путь пакета выходит за каталог плагина")
            snapshots[path] = read_bytes(path)
            if snapshots[path] is not None and hashlib.sha256(snapshots[path]).hexdigest() != checksum:
                raise ThorError("Файлы плагина изменены извне; сохраните изменения перед обновлением")
            changes[path] = None
        changes[marker] = None
    if not uninstall:
        if package is None:
            raise ThorError("Укажите --package")
        with zipfile.ZipFile(package) as archive:
            entries = archive.infolist()
            if sum(entry.file_size for entry in entries) > 32 * 1024 * 1024 or len(entries) > 500:
                raise ThorError("Пакет слишком большой")
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise ThorError("Дублирующиеся пути в ZIP")
            metadata = json.loads(archive.read("ThorFG/thorfg-package.json"))
            if metadata.get("name") != "ThorFG":
                raise ThorError("Это не пакет ThorFG")
            files = metadata["files"]
            if set(names) != {"ThorFG/" + name for name in files} | {"ThorFG/thorfg-package.json"}:
                raise ThorError("Состав пакета не соответствует manifest")
            for name, checksum in files.items():
                path = paths.safe(target / name)
                if not path.is_relative_to(target) or "\\" in name or Path(name).is_absolute():
                    raise ThorError("Небезопасный путь в ZIP")
                value = archive.read("ThorFG/" + name)
                if hashlib.sha256(value).hexdigest() != checksum:
                    raise ThorError("SHA-256 файла плагина не совпадает")
                if path.exists() and (not previous or name not in previous["files"]):
                    raise ThorError("Пакет перезаписал бы посторонний файл")
                if path not in snapshots:
                    snapshots[path] = read_bytes(path)
                changes[path] = value
            changes[marker] = archive.read("ThorFG/thorfg-package.json")
    with Store(paths).lock():
        Store(paths).apply(changes, expected=snapshots, kind="decky-uninstall" if uninstall else "decky-install")


def main():
    parser = argparse.ArgumentParser(description="Установка только ThorFG в Decky")
    parser.add_argument("mode", choices=["install", "update", "uninstall"])
    parser.add_argument("--package", type=Path)
    parser.add_argument("--decky-home", type=Path, help="Фактический каталог homebrew (по умолчанию ~/homebrew)")
    args = parser.parse_args()
    paths = Paths.environment(decky_root=args.decky_home)
    try:
        deploy(paths, args.package, args.mode == "uninstall")
    except (OSError, ValueError, KeyError, ThorError, zipfile.BadZipFile) as exc:
        print("Ошибка установки:", exc, file=sys.stderr)
        return 1
    print("Операция завершена. Перезагрузите ThorFG через интерфейс Decky.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
