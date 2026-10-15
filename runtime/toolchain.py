"""LLVM/CMake: явные инструменты, проверка кэша и наблюдаемые build metadata."""
from pathlib import Path
import re
import shutil
import subprocess

from thorfg.paths import ThorError

TOOLS = ("clang++", "llvm-ar", "llvm-ranlib", "cmake", "ninja", "readelf", "nm", "file")


def output(*args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30).stdout.strip()


def discover_tools():
    tools = {}
    for name in TOOLS:
        path = shutil.which(name)
        if not path:
            raise ThorError("Не найден " + name + "; установите llvm/clang/cmake/ninja-build/binutils/file внутри Distrobox")
        tools[name] = str(Path(path).absolute())
    return tools


def cmake_arguments(checkout, build, tools):
    return [tools["cmake"], "-S", str(checkout), "-B", str(build), "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_COMPILER=" + tools["clang++"],
            "-DCMAKE_AR=" + tools["llvm-ar"], "-DCMAKE_RANLIB=" + tools["llvm-ranlib"],
            "-DCMAKE_CXX_COMPILER_AR=" + tools["llvm-ar"],
            "-DCMAKE_CXX_COMPILER_RANLIB=" + tools["llvm-ranlib"],
            "-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON", "-DLSFGVK_BUILD_UI=OFF", "-DLSFGVK_BUILD_CLI=ON"]


def read_cache(build):
    cache_path = build / "CMakeCache.txt"
    if cache_path.is_symlink() or not cache_path.is_file():
        raise ThorError("Нет CMakeCache.txt: невозможно подтвердить существующую сборку")
    entries = {}
    for line in cache_path.read_text("utf-8").splitlines():
        match = re.match(r"([^#/:][^:=]*):[^=]+=(.*)$", line)
        if match:
            entries[match[1]] = match[2]
    return entries


def validate_cache(checkout, build, *, completed=False):
    cache = read_cache(build)
    if Path(cache.get("CMAKE_HOME_DIRECTORY", "")).resolve() != checkout.resolve():
        raise ThorError("CMake cache относится к другому source directory")
    if cache.get("CMAKE_GENERATOR") != "Ninja" or cache.get("CMAKE_BUILD_TYPE") != "Release":
        raise ThorError("Ожидался Ninja/Release cache")
    for key in ("CMAKE_AR", "CMAKE_RANLIB", "CMAKE_CXX_COMPILER_AR", "CMAKE_CXX_COMPILER_RANLIB"):
        value = cache.get(key, "")
        if not value or "NOTFOUND" in value:
            raise ThorError("Ошибочный CMake cache (" + key + "). Выберите новый --build-dir; старый каталог сохранён")
        if completed and not Path(value).name.startswith("llvm-"):
            raise ThorError("Существующая LTO-сборка не подтверждает LLVM ar/ranlib")
    if completed:
        if cache.get("CMAKE_INTERPROCEDURAL_OPTIMIZATION", "").upper() not in ("ON", "TRUE", "1"):
            raise ThorError("В cache не подтверждено LTO")
        if not (build / "build.ninja").is_file() or not (build / ".ninja_log").is_file():
            raise ThorError("Недостаточно Ninja metadata для восстановления")
        link_entries = [line for line in (build / ".ninja_log").read_text("utf-8").splitlines()
                        if len(line.split("\t")) >= 5 and line.split("\t")[3] == "lsfg-vk-layer/liblsfg-vk-layer.so"]
        if not link_entries:
            raise ThorError("В Ninja log отсутствует завершённая линковка layer")
    compiler_metadata = {}
    for path in sorted((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake")):
        text = path.read_text("utf-8")
        for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION"):
            match = re.search(r'set\(' + key + r' "([^"]+)"\)', text)
            if match:
                compiler_metadata[key] = match[1]
    if completed and (compiler_metadata.get("CMAKE_CXX_COMPILER_ID") != "Clang" or not compiler_metadata.get("CMAKE_CXX_COMPILER_VERSION")):
        raise ThorError("Недостаточно сохранённых данных компилятора Clang")
    return {"cache_generator": cache["CMAKE_GENERATOR"], "cache_build_type": cache["CMAKE_BUILD_TYPE"],
            "compiler_id_recorded": compiler_metadata.get("CMAKE_CXX_COMPILER_ID"),
            "compiler_version_recorded": compiler_metadata.get("CMAKE_CXX_COMPILER_VERSION"),
            "cmake_cache_version": ".".join(cache.get("CMAKE_CACHE_" + part + "_VERSION", "unknown") for part in ("MAJOR", "MINOR", "PATCH")),
            "llvm_tools_in_cache": {key: Path(cache[key]).name for key in ("CMAKE_AR", "CMAKE_RANLIB", "CMAKE_CXX_COMPILER_AR", "CMAKE_CXX_COMPILER_RANLIB")}}
