import json
import subprocess
from unittest.mock import patch

from test_thorfg import Base
from scripts.safe_update import backup, safe, update, REPOSITORY


class SafeUpdateTests(Base):
    def test_backup_preserves_local_runtime_edits_and_build_result(self):
        repo = self.home / "thorfg"
        self.put(repo / "runtime/build.py", "local build recipe")
        self.put(repo / "runtime/sources.lock.json", "local mirror")
        binary = self.put(repo / ".build/historical/build-llvm/lsfg-vk-layer/liblsfg-vk-layer.so", b"existing native build")
        with patch("scripts.safe_update.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"binary diff")):
            directory, changed = backup(repo)
        self.assertTrue(changed)
        self.assertEqual((directory / "tracked.patch").read_bytes(), b"binary diff")
        self.assertEqual((directory / "build.py").read_text(), "local build recipe")
        self.assertEqual((directory / "sources.lock.json").read_text(), "local mirror")
        self.assertEqual(binary.read_bytes(), b"existing native build")

    def test_update_stashes_tracked_changes_without_untracked_or_clean(self):
        repo = self.home / "thorfg"
        self.put(repo / "runtime/build.py", "local")
        commands = []
        def git_call(root, *args):
            commands.append(args)
            return {("rev-parse", "--show-toplevel"): str(repo), ("remote", "get-url", "origin"): REPOSITORY,
                    ("branch", "--show-current"): "master", ("rev-parse", "HEAD"): "a" * 40,
                    ("rev-parse", "FETCH_HEAD"): "b" * 40, ("rev-parse", "refs/stash"): "c" * 40}.get(args, "")
        with patch("scripts.safe_update.git", side_effect=git_call), patch("scripts.safe_update.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"diff")):
            record = update(repo, "feat/runtime-recovery-probe")
        self.assertEqual(record["stash"], "c" * 40)
        self.assertTrue(any(args[:2] == ("stash", "push") for args in commands))
        self.assertFalse(any("reset" in args or "clean" in args or "--include-untracked" in args or "-u" in args for args in commands))

    def test_target_cannot_overwrite_ignored_build_directory(self):
        repo = self.home / "thorfg"
        binary = self.put(repo / ".build/historical/build-llvm/layer.so", b"keep")
        commands = []
        def git_call(root, *args):
            commands.append(args)
            if args[0] == "ls-tree":
                return ".build/historical/build-llvm/layer.so"
            return {("rev-parse", "--show-toplevel"): str(repo),
                    ("remote", "get-url", "origin"): REPOSITORY,
                    ("rev-parse", "FETCH_HEAD"): "b" * 40}.get(args, "")
        with patch("scripts.safe_update.git", side_effect=git_call), \
                patch("scripts.safe_update.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"diff")), \
                self.assertRaises(ValueError):
            update(repo, "master")
        self.assertFalse(any(args[0] in ("stash", "switch") for args in commands))
        self.assertEqual(binary.read_bytes(), b"keep")
