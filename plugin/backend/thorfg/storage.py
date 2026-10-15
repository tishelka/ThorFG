"""Атомарная запись, кооперативная блокировка и журнал восстановления."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from .paths import Paths, ThorError


def read_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def atomic(path: Path, value: bytes | None, paths: Paths):
    path = paths.safe(path)
    if value is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".thorfg-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name == "posix":
            dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encode(value):
    return None if value is None else base64.b64encode(value).decode("ascii")


def decode(value):
    return None if value is None else base64.b64decode(value, validate=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class Store:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.pending = paths.state / "pending.json"

    def target(self, path):
        path = self.paths.safe(path)
        exact = (self.paths.settings, self.paths.config, self.paths.manifest)
        roots = (self.paths.runtimes, self.paths.decky_root / "plugins/ThorFG")
        if path not in exact and not any(path.is_relative_to(root) and path != root for root in roots):
            raise ThorError("Журнал не может изменять файлы вне компонентов ThorFG")
        return path

    @contextmanager
    def lock(self, recovery=False):
        lock = self.paths.safe(self.paths.state / "write.lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.mkdir()
        except FileExistsError as exc:
            raise ThorError("ThorFG занят. Если процесс аварийно завершён, проверьте write.lock по инструкции") from exc
        try:
            if self.paths.safe(self.pending).exists() and not recovery:
                raise ThorError("Обнаружена незавершённая операция; выполните rollback")
            yield
        finally:
            lock.rmdir()

    def apply(self, changes: dict[Path, bytes | None], expected=None, kind="configuration"):
        """Вызывать под lock; expected — снимок на момент чтения конфигурации."""
        entries = []
        for path, after in changes.items():
            path = self.target(path)
            before = read_bytes(path)
            if expected is not None and path in expected and expected[path] != before:
                raise ThorError("Файл изменён другим приложением; перечитайте состояние")
            if before != after:
                entries.append({"path": str(path.relative_to(self.paths.home)),
                                "before": encode(before), "after": encode(after)})
        if not entries:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        record = {"id": stamp + "-" + uuid.uuid4().hex, "kind": kind,
                  "entries": entries, "rolled_back": False}
        atomic(self.pending, json_bytes(record), self.paths)
        completed = []
        try:
            for entry in entries:
                path = self.paths.home / entry["path"]
                if read_bytes(path) != decode(entry["before"]):
                    raise ThorError("Обнаружено параллельное изменение файла")
                completed.append(entry)
                atomic(path, decode(entry["after"]), self.paths)
            history = self.paths.state / "history" / (record["id"] + ".json")
            atomic(history, json_bytes(record), self.paths)
        except BaseException:
            for entry in reversed(completed):
                path = self.paths.home / entry["path"]
                current = read_bytes(path)
                if current == decode(entry["before"]):
                    continue
                if current != decode(entry["after"]):
                    raise ThorError("Конфликт при восстановлении; сохранён pending.json")
                atomic(path, decode(entry["before"]), self.paths)
            atomic(self.pending, None, self.paths)
            raise
        atomic(self.pending, None, self.paths)

    def rollback(self):
        with self.lock(recovery=True):
            source = self.pending if self.pending.exists() else None
            pending = source is not None
            if source is None:
                history = self.paths.safe(self.paths.state / "history")
                for candidate in sorted(history.glob("*.json"), reverse=True):
                    self.paths.safe(candidate)
                    if not json.loads(candidate.read_text("utf-8"))["rolled_back"]:
                        source = candidate
                        break
            if source is None:
                raise ThorError("Резервных копий для отката нет")
            record = json.loads(source.read_text("utf-8"))
            if not isinstance(record.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", record["id"]):
                raise ThorError("Некорректный идентификатор журнала восстановления")
            for entry in record["entries"]:
                path = self.target(self.paths.home / entry["path"])
                allowed = [decode(entry["after"])]
                if pending:
                    allowed.append(decode(entry["before"]))
                if read_bytes(path) not in allowed:
                    raise ThorError("После операции файл изменён извне; автоматический откат остановлен")
            # Сам откат также восстанавливаем после остановки процесса.
            if not pending:
                atomic(self.pending, json_bytes(record), self.paths)
            for entry in reversed(record["entries"]):
                atomic(self.paths.home / entry["path"], decode(entry["before"]), self.paths)
            record["rolled_back"] = True
            atomic(self.paths.state / "history" / (record["id"] + ".json"),
                   json_bytes(record), self.paths)
            atomic(self.pending, None, self.paths)
            return record["kind"]
