#!/usr/bin/env python3
"""Небольшой переносимый архив исходников без Windows venv и node_modules."""
import gzip
import hashlib
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [path for path in ROOT.iterdir() if path.is_file() and path.suffix != ".log"]
    for directory in ("plugin", "scripts", "runtime", "docs", "tests", "examples", ".github"):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file()
                     and not {"node_modules", "__pycache__", ".git"}.intersection(path.parts)
                     and path.suffix not in (".pyc", ".map"))
    output = ROOT / "artifacts/ThorFG-source.tar.gz"
    output.parent.mkdir(exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w|") as archive:
            for path in sorted(set(files)):
                if path.is_symlink():
                    raise SystemExit("Символические ссылки не включаются в переносимый архив")
                info = archive.gettarinfo(str(path), "thorfg/" + path.relative_to(ROOT).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".gz.sha256").write_text(digest + "  " + output.name + "\n", encoding="utf-8")
    print("Архив исходников:", output)
    print("SHA-256:", digest)


if __name__ == "__main__":
    main()
