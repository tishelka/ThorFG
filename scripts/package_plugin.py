#!/usr/bin/env python3
"""Создание локального пакета разработки; runtime и коммерческие файлы исключены."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Упаковать ThorFG для ручного тестирования Decky")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ThorFG-dev.zip")
    args = parser.parse_args()
    plugin = ROOT / "plugin"
    if not (plugin / "dist/index.js").is_file():
        raise SystemExit("Сначала выполните npm ci и npm run build в plugin/")
    # tomlkit — pure Python; копируем установленную закреплённую версию с лицензией.
    import importlib.metadata
    import tomlkit
    if importlib.metadata.version("tomlkit") != "0.13.3":
        raise SystemExit("Установите зависимости из requirements.txt")
    vendor = plugin / "py_modules"
    vendor.mkdir(exist_ok=True)
    shutil.copytree(Path(tomlkit.__file__).parent, vendor / "tomlkit", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    dist = importlib.metadata.distribution("tomlkit")
    for entry in dist.files or []:
        if "LICENSE" in str(entry).upper():
            shutil.copyfile(dist.locate_file(entry), vendor / "tomlkit-LICENSE")
            break
    if not (vendor / "tomlkit-LICENSE").is_file():
        raise SystemExit("Лицензия tomlkit не найдена")
    files = [plugin / name for name in ("main.py", "plugin.json", "package.json", "dist/index.js")]
    for folder in ("backend", "py_modules"):
        files.extend(path for path in (plugin / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    contents = {str(path.relative_to(plugin)).replace("\\", "/"): path.read_bytes() for path in files}
    contents["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    contents["THIRD_PARTY_NOTICES.md"] = (ROOT / "THIRD_PARTY_NOTICES.md").read_bytes()
    for package, license_file in (("@decky/api", "LICENSE"), ("react-icons", "LICENSE"),
                                   ("tslib", "LICENSE.txt")):
        source = plugin / "node_modules" / package / license_file
        if not source.is_file():
            raise SystemExit("Не найдена лицензия npm-компонента: " + package)
        contents["licenses/" + package.replace("/", "-") + ".txt"] = source.read_bytes()
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}
    contents["thorfg-package.json"] = json.dumps({"name": "ThorFG", "version": "0.1.0-dev",
        "hardware_verified": False, "files": hashes}, indent=2).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(contents.items()):
            info = zipfile.ZipInfo("ThorFG/" + name, date_time=(2026, 10, 15, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".zip.sha256").write_text(digest + "  " + args.output.name + "\n", encoding="utf-8")
    print("Пакет разработки:", args.output)
    print("SHA-256:", digest)


if __name__ == "__main__":
    main()
