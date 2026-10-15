"""HOME/XDG и разрешённый alias корня; все записи — только во временном home."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/backend"))

from thorfg.paths import Paths, ThorError
from thorfg.storage import atomic


class PathsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "user"
        self.home.mkdir()
        environment = patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("XDG_DATA_HOME", None)

    def symlink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("У пользователя Windows нет права создавать symlink")
            raise  # В Linux ошибка symlink не должна скрываться за skip.

    def test_xdg_absent_uses_canonical_home_defaults(self):
        paths = Paths.environment()
        self.assertEqual(paths.home, self.home)
        self.assertEqual(paths.config_root, self.home / ".config")
        self.assertEqual(paths.data_root, self.home / ".local/share")
        self.assertEqual(paths.decky_root, self.home / "homebrew")

    def test_empty_xdg_uses_defaults(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "", "XDG_DATA_HOME": ""}):
            paths = Paths.environment(self.home)
        self.assertEqual(paths.config_root, self.home / ".config")
        self.assertEqual(paths.data_root, self.home / ".local/share")

    def test_absolute_xdg_within_home_is_used_without_creating_files(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home / "config"),
                                     "XDG_DATA_HOME": str(self.home / "data")}):
            paths = Paths.environment(self.home)
        self.assertEqual(paths.config, self.home / "config/lsfg-vk/conf.toml")
        self.assertEqual(paths.manifest, self.home / "data/vulkan/implicit_layer.d/ThorFG.json")
        self.assertEqual(paths.runtimes, self.home / "data/thorfg/runtimes")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_each_foreign_xdg_is_rejected(self):
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            with self.subTest(name=name), patch.dict(os.environ, {name: str(self.root / "foreign")}):
                with self.assertRaises(ThorError):
                    Paths.environment(self.home)
        self.assertFalse((self.root / "foreign").exists())

    def test_relative_xdg_is_ignored_as_required_by_xdg_spec(self):
        for value in ("relative", "./config", "../foreign"):
            with self.subTest(value=value), patch.dict(os.environ, {
                    "XDG_CONFIG_HOME": value, "XDG_DATA_HOME": value}):
                paths = Paths.environment(self.home)
                self.assertEqual(paths.config_root, self.home / ".config")
                self.assertEqual(paths.data_root, self.home / ".local/share")

    def test_absolute_xdg_traversal_is_rejected(self):
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            with self.subTest(name=name), patch.dict(os.environ, {name: str(self.home / "sub/../config")}):
                with self.assertRaises(ThorError):
                    Paths.environment(self.home)

    def test_explicit_decky_home_does_not_use_ambient_home(self):
        runner = self.root / "runner"
        with patch.dict(os.environ, {"HOME": str(runner), "USERPROFILE": str(runner)}):
            paths = Paths.environment(self.home, self.home / "custom-homebrew")
        self.assertEqual(paths.home, self.home)
        self.assertEqual(paths.decky_root, self.home / "custom-homebrew")

    def test_decky_home_outside_home_is_rejected(self):
        with self.assertRaises(ThorError):
            Paths.environment(self.home, self.root / "other-homebrew")

    def test_home_must_be_absolute_and_without_parent_transitions(self):
        for home in (Path("relative"), self.home / "sub/.."):
            with self.subTest(home=home), self.assertRaises(ThorError):
                Paths(home)

    def test_system_home_alias_is_canonicalized_for_xdg_and_decky(self):
        alias = self.root / "home-alias"
        self.symlink(alias, self.home)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(alias / ".config"),
                                     "XDG_DATA_HOME": str(alias / ".local/share")}):
            paths = Paths.environment(alias, alias / "homebrew")
        self.assertEqual(paths.home, self.home)
        self.assertEqual(paths.decky_root, self.home / "homebrew")
        self.assertEqual(paths.config_root, self.home / ".config")
        self.assertEqual(paths.safe(alias / "homebrew/plugins/ThorFG/plugin.json"),
                         self.home / "homebrew/plugins/ThorFG/plugin.json")
        atomic(paths.settings, b"{}", paths)
        self.assertEqual((self.home / ".config/thorfg/settings.json").read_bytes(), b"{}")

    def test_symlinked_home_parent_like_fedora_home_var_home(self):
        real_parent = self.root / "var-home"
        real_home = real_parent / "user"
        real_home.mkdir(parents=True)
        alias_parent = self.root / "home"
        self.symlink(alias_parent, real_parent)
        paths = Paths.environment(alias_parent / "user", alias_parent / "user/homebrew")
        self.assertEqual(paths.home, real_home)
        self.assertEqual(paths.decky_root, real_home / "homebrew")

    def test_unrelated_alias_is_rejected_even_when_it_targets_home(self):
        alias = self.root / "untrusted"
        self.symlink(alias, self.home)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(alias / ".config")}):
            with self.assertRaises(ThorError):
                Paths.environment(self.home)

    def test_symlink_below_trusted_home_alias_is_still_rejected(self):
        alias = self.root / "trusted-home"
        self.symlink(alias, self.home)
        outside = self.root / "outside"
        outside.mkdir()
        self.symlink(self.home / "config", outside)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(alias / "config")}):
            with self.assertRaises(ThorError):
                Paths.environment(alias, alias / "homebrew")
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_to_another_directory_inside_home_is_rejected(self):
        target = self.home / "real-config"
        target.mkdir()
        self.symlink(self.home / ".config", target)
        with self.assertRaises(ThorError):
            Paths.environment(self.home)

    def test_dangling_symlink_and_path_traversal_cannot_be_written(self):
        paths = Paths.environment(self.home)
        self.symlink(self.home / "link", self.root / "missing")
        for path in (self.home / "link/file", self.home / "sub/../file", self.root / "outside"):
            with self.subTest(path=path), self.assertRaises(ThorError):
                atomic(path, b"blocked", paths)
        self.assertFalse((self.root / "missing").exists())


if __name__ == "__main__":
    unittest.main()
