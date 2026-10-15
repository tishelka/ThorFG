from dataclasses import dataclass, field
import os
from pathlib import Path


class ThorError(Exception):
    """Ошибка, которую можно показать пользователю."""


def guarded(path: Path, root: Path) -> Path:
    root = root.resolve()
    if ".." in path.parts:
        raise ThorError("Родительские переходы в пути записи запрещены")
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root) or path == root:
        raise ThorError("Путь выходит за разрешённый пользовательский каталог")
    if path.resolve(strict=False) != path:
        raise ThorError("Запись через перенаправленный путь запрещена")
    current = path
    while current != root:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ThorError("Запись через символическую ссылку или junction запрещена")
        current = current.parent
    return path


@dataclass(frozen=True)
class Paths:
    home: Path
    config_root: Path | None = None
    data_root: Path | None = None
    decky_root: Path | None = None
    _home_alias: Path = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        declared_home = Path(self.home)
        if not declared_home.is_absolute() or ".." in declared_home.parts:
            raise ThorError("Домашний каталог должен быть абсолютным путём без ..")
        # Только явно переданный HOME — доверенный корень. Его системный alias
        # (/home -> /var/home на Fedora) разрешаем до проверки дочерних путей.
        object.__setattr__(self, "_home_alias", declared_home)
        object.__setattr__(self, "home", declared_home.resolve())
        for field, default in (("config_root", self.home / ".config"),
                               ("data_root", self.home / ".local/share"),
                               ("decky_root", self.home / "homebrew")):
            value = getattr(self, field) or default
            object.__setattr__(self, field, self.safe(value))

    @classmethod
    def environment(cls, home: Path | None = None, decky_root: Path | None = None):
        def xdg(name):
            value = os.environ.get(name)
            return Path(value) if value and Path(value).is_absolute() else None
        return cls(home or Path.home(), xdg("XDG_CONFIG_HOME"),
                   xdg("XDG_DATA_HOME"), decky_root)

    @property
    def state(self):
        return self.config_root / "thorfg"

    @property
    def settings(self):
        return self.state / "settings.json"

    @property
    def config(self):
        return self.config_root / "lsfg-vk/conf.toml"

    @property
    def runtimes(self):
        return self.data_root / "thorfg/runtimes"

    @property
    def manifest(self):
        return self.data_root / "vulkan/implicit_layer.d/ThorFG.json"

    def safe(self, path):
        path = Path(path)
        if ".." in path.parts:
            raise ThorError("Родительские переходы в пути записи запрещены")
        if path.is_relative_to(self._home_alias):
            # Не resolve() произвольного кандидата: ссылки ниже HOME по-прежнему
            # проверяются guarded(), даже если ведут обратно внутрь HOME.
            path = self.home / path.relative_to(self._home_alias)
        return guarded(path, self.home)
