"""Чтение ELF-заголовков без загрузки или исполнения библиотеки."""
import struct
from pathlib import Path

from .paths import ThorError


def elf_info(path: Path):
    with path.open("rb") as stream:
        header = stream.read(64)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] not in (1, 2) or header[5] not in (1, 2):
        raise ThorError("Файл не является поддерживаемым ELF")
    kind, machine = struct.unpack_from("<HH" if header[5] == 1 else ">HH", header, 16)
    return {"architecture": {183: "aarch64", 62: "x86_64", 3: "i386", 40: "arm"}.get(machine, f"ELF-{machine}"),
            "bits": 64 if header[4] == 2 else 32, "little_endian": header[5] == 1,
            "shared_object": kind == 3, "header_complete": len(header) >= (64 if header[4] == 2 else 52),
            "version": header[6]}


def elf(path: Path):
    info = elf_info(path)
    if not (info["bits"] == 64 and info["little_endian"] and info["header_complete"] and info["version"] == 1):
        raise ThorError("Требуется ELF64 little-endian shared object")
    if not info["shared_object"] or info["architecture"] != "aarch64":
        raise ThorError("Библиотека не является AArch64 ELF shared object")
    return "aarch64"
