"""Ограниченный парсер Valve KeyValues без исполнения содержимого manifest."""
from pathlib import Path
import re

from .paths import ThorError


TOKEN = re.compile(r'\s+|//[^\n]*|"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)')


def vdf(text: str):
    if len(text) > 2_000_000:
        raise ThorError("Steam manifest слишком большой")
    tokens = []
    offset = 0
    for match in TOKEN.finditer(text):
        if match.start() != offset:
            raise ThorError("Повреждён Steam manifest")
        offset = match.end()
        if match.group(1) is not None:
            # VDF использует \\ и \"; не декодируем произвольные escape sequences.
            tokens.append(("s", re.sub(r'\\([\\"])', r'\1', match.group(1))))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
        elif match.group(3):
            tokens.append(("s", match.group(3)))
    if offset != len(text):
        raise ThorError("Повреждён Steam manifest")
    position = 0

    def parse(depth=0, nested=False):
        nonlocal position
        if depth > 32:
            raise ThorError("Слишком глубокий Steam manifest")
        result = {}
        while position < len(tokens):
            kind, key = tokens[position]
            position += 1
            if kind == "}" and nested:
                return result
            if kind != "s" or position >= len(tokens) or key in result:
                raise ThorError("Некорректная структура Steam manifest")
            kind, value = tokens[position]
            position += 1
            if kind == "{":
                value = parse(depth + 1, True)
            elif kind != "s":
                raise ThorError("Некорректное значение Steam manifest")
            result[key] = value
        if nested:
            raise ThorError("Steam manifest не завершён")
        return result
    return parse()


def load(path: Path):
    if path.stat().st_size > 2_000_000:
        raise ThorError("Steam manifest слишком большой")
    return vdf(path.read_text("utf-8-sig"))


class Steam:
    def __init__(self, home: Path):
        self.home = home
        self.warnings = []

    def libraries(self):
        roots = [self.home / ".local/share/Steam", self.home / ".steam/steam",
                 self.home / ".steam/root"]
        found = {root.resolve() for root in roots if root.is_dir()}
        for root in list(found):
            for filename in (root / "steamapps/libraryfolders.vdf", root / "config/libraryfolders.vdf"):
                if not filename.is_file():
                    continue
                try:
                    items = load(filename).get("libraryfolders", {})
                    for key, value in items.items():
                        if not key.isdecimal():
                            continue
                        raw = value.get("path") if isinstance(value, dict) else value
                        if isinstance(raw, str) and Path(raw).is_absolute() and Path(raw).is_dir():
                            found.add(Path(raw).resolve())
                except (OSError, ValueError, ThorError, AttributeError):
                    self.warnings.append("Не удалось прочитать libraryfolders.vdf")
        return sorted(found)

    def games(self):
        games = {}
        for library in self.libraries():
            for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
                try:
                    app = load(manifest)["AppState"]
                    appid, directory = app["appid"], app["installdir"]
                    if not isinstance(appid, str) or not appid.isdecimal():
                        raise ThorError("Неверный Steam App ID")
                    if manifest.name != f"appmanifest_{appid}.acf":
                        raise ThorError("App ID не соответствует manifest")
                    if not isinstance(directory, str) or not directory or any(
                            c in directory for c in ("/", "\\", "\0")) or directory in (".", ".."):
                        raise ThorError("Неверный installdir")
                    common = (library / "steamapps/common").resolve()
                    install = (common / directory).resolve()
                    if not install.is_relative_to(common) or not install.is_dir():
                        raise ThorError("Каталог игры отсутствует или выходит за Steam library")
                    games.setdefault(appid, {"appid": appid, "name": str(app["name"])[:200],
                                             "install_dir": str(install)})
                except (KeyError, TypeError, OSError, ValueError, ThorError):
                    self.warnings.append("Пропущен повреждённый или недоступный appmanifest")
        return sorted(games.values(), key=lambda game: game["name"].casefold())

    def executables(self, appid: str):
        game = next((game for game in self.games() if game["appid"] == appid), None)
        if game is None:
            raise ThorError("Установленная игра не найдена")
        root = Path(game["install_dir"])
        results, count = [], 0
        # os.walk не проходит по symlink-каталогам; ограничиваем число файлов.
        import os
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                count += 1
                if count > 30_000:
                    return results
                path = Path(directory) / name
                if path.suffix.casefold() == ".exe" and not path.is_symlink():
                    results.append(str(path.relative_to(root)).replace("\\", "/"))
                    if len(results) >= 300:
                        return results
        return results

    def dll(self, modern=False, configured=None):
        filename = "lsfg-vk.dll" if modern else "Lossless.dll"
        if configured:
            path = Path(configured).expanduser()
            if path.is_file() and path.name.casefold() == filename.casefold():
                return str(path.resolve())
        for game in self.games():
            if game["appid"] == "993090":
                candidate = Path(game["install_dir"]) / filename
                if candidate.is_file():
                    return str(candidate)
        return None
