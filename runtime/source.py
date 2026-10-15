"""Закреплённые исходники: зеркало меняет transport, но не commit/tree."""
import json
import os
from pathlib import Path
import subprocess
import uuid

from thorfg.bundle import REPOSITORIES, SOURCES, TREES
from thorfg.paths import ThorError, guarded


def git(checkout, *args, network=False):
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(checkout), *args],
                            check=True, capture_output=True, text=True, encoding="utf-8", timeout=90,
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "0" if network else "1"})
    return result.stdout.strip()


def load_source(root, variant):
    source = json.loads((root / "runtime/sources.lock.json").read_text("utf-8"))[variant]
    expected = SOURCES.get(source.get("commit"))
    if not expected or (source["adapter"], source["version"], source["api_version"]) != expected:
        raise ThorError("Закреплённая версия не соответствует адаптеру")
    if source.get("tree") != TREES[source["commit"]]:
        raise ThorError("Git tree в lockfile не совпадает с проверенным upstream")
    repositories = [source["repository"], *source.get("mirrors", [])]
    if not repositories or not set(repositories) <= REPOSITORIES[source["adapter"]]:
        raise ThorError("В lockfile обнаружен источник вне проверенного списка")
    return source


def verify_checkout(checkout, source, build=None):
    checkout = checkout.resolve()
    if Path(git(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout:
        raise ThorError("Указан не корень upstream checkout")
    if git(checkout, "rev-parse", "HEAD") != source["commit"]:
        raise ThorError("Checkout имеет другой commit SHA; автоматическое переключение запрещено")
    if git(checkout, "rev-parse", "HEAD^{tree}") != source["tree"]:
        raise ThorError("Не совпадает Git tree upstream")
    origin = git(checkout, "remote", "get-url", "origin")
    if origin not in REPOSITORIES[source["adapter"]]:
        raise ThorError("Origin checkout отсутствует в списке доверенных источников")
    if git(checkout, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", "."):
        raise ThorError("Upstream checkout содержит изменения tracked-файлов")
    # /build игнорируется upstream. Пользовательский build-llvm разрешён только
    # как явно выбранный build directory; прочие untracked source-файлы запрещены.
    for name in git(checkout, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if not name:
            continue
        path = checkout / name
        if build is None or not path.is_relative_to(build):
            raise ThorError("Upstream checkout содержит непредусмотренные untracked-файлы")
    submodules = git(checkout, "submodule", "status", "--recursive")
    if any(line.startswith(("-", "+", "U")) for line in submodules.splitlines()):
        raise ThorError("Submodules не соответствуют закреплённой ревизии")
    return {"source_repository": origin, "source_tree": source["tree"], "commit": source["commit"],
            "tracked_clean": True, "untracked_policy": "only selected build directory"}


def acquire(root, source, destination, preferred=None):
    destination = guarded(destination, root)
    if destination.exists():
        raise ThorError("Checkout уже существует: используйте --use-existing-checkout и --resume либо --package-existing")
    repositories = [source["repository"], *source.get("mirrors", [])]
    if preferred:
        if preferred not in repositories:
            raise ThorError("Выбранное зеркало отсутствует в закреплённом списке")
        repositories = [preferred, *[url for url in repositories if url != preferred]]
    destination.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    for repository in repositories:
        candidate = guarded(destination.parent / ("fetch-" + uuid.uuid4().hex), root)
        try:
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "--branch",
                            source["branch"], repository, str(candidate)], check=True, timeout=300)
            git(candidate, "checkout", "--detach", source["commit"], network=True)
            git(candidate, "submodule", "update", "--init", "--recursive", network=True)
            verify_checkout(candidate, source)
        except (subprocess.SubprocessError, OSError, ThorError) as exc:
            failures.append(type(exc).__name__)
            print("Источник не прошёл загрузку/проверку; частичный checkout сохранён:", candidate)
            continue
        if destination.exists():
            raise ThorError("Назначение checkout появилось во время загрузки")
        candidate.rename(destination)
        return destination
    raise ThorError("Все закреплённые источники недоступны или не прошли проверку: " + ", ".join(failures))
