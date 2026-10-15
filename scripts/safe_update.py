#!/usr/bin/env python3
"""Сохраняет рабочие изменения и переключает на новую тестовую ветку. Без reset/clean."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPOSITORY = "https://github.com/tishelka/ThorFG.git"


def git(repo, *args):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8", timeout=120).stdout.strip()


def safe(repo, path):
    if ".." in path.parts or not path.is_relative_to(repo) or path == repo or path.resolve() != path:
        raise ValueError("Небезопасный путь резервной копии")
    current = path
    while current != repo:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("Ссылка в пути резервной копии")
        current = current.parent
    return path


def backup(repo):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = safe(repo, repo / ".build/update-backups" / stamp)
    directory.mkdir(parents=True, mode=0o700)
    os.chmod(directory, 0o700)
    diff = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), "diff",
                           "--no-ext-diff", "--no-textconv", "--binary", "HEAD"],
                          check=True, capture_output=True, timeout=30).stdout
    (directory / "tracked.patch").write_bytes(diff)
    for name in ("build.py", "sources.lock.json"):
        source = repo / "runtime" / name
        if source.is_file() and not source.is_symlink():
            (directory / name).write_bytes(source.read_bytes())
    return directory, bool(diff)


def update(repo, ref):
    if not repo.is_absolute() or ".." in repo.parts:
        raise ValueError("Нужен абсолютный путь к checkout без ..")
    home = Path.home().resolve()
    repo = repo.resolve()
    if not repo.is_relative_to(home) or repo == home:
        raise ValueError("Checkout должен находиться внутри HOME")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", ref) or ".." in ref or ref.startswith(("-", "/")):
        raise ValueError("Некорректный Git ref")
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("Укажите корень ThorFG checkout")
    if git(repo, "remote", "get-url", "origin") != REPOSITORY:
        raise ValueError("Origin не соответствует ThorFG")
    if git(repo, "ls-files", "--", ".build"):
        raise ValueError(".build ошибочно содержит tracked-файлы; автоматическое обновление остановлено")
    directory, changed = backup(repo)
    original_head = git(repo, "rev-parse", "HEAD")
    original_branch = git(repo, "branch", "--show-current")
    print("Резервные копии сохранены локально:", directory)
    # При ошибке сети рабочая копия ещё не менялась, backup уже существует.
    git(repo, "fetch", "origin", ref)
    target = git(repo, "rev-parse", "FETCH_HEAD")
    if git(repo, "ls-tree", "-r", "--name-only", target, "--", ".build"):
        raise ValueError("Целевая ревизия содержит tracked .build; рабочая копия оставлена без изменений")
    stash = None
    if changed:
        git(repo, "stash", "push", "-m", "ThorFG safe update " + directory.name)
        stash = git(repo, "rev-parse", "refs/stash")
    record = {"original_head": original_head, "original_branch": original_branch,
              "target": target, "requested_ref": ref, "stash": stash,
              "note": "Ignored .build and all untracked files are never cleaned or stashed"}
    (directory / "update.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Новая ветка оставляет исходную branch ref на месте. Git откажется перезаписывать
    # конфликтующие untracked-файлы; никакого force/reset/clean и автоприменения старого builder.
    branch = "thorfg-test-" + directory.name
    git(repo, "switch", "-c", branch, target)
    print("Обновление получено в отдельную локальную ветку:", branch)
    print(".build/historical/build-llvm сохранён. Старый diff не применялся автоматически.")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Безопасно получить обновление ThorFG с сохранением локального diff")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--ref", default="master")
    args = parser.parse_args(argv)
    try:
        update(args.repo, args.ref)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("Обновление остановлено; reset/clean не выполнялись:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
