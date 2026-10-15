"""Тесты работают только во временных каталогах; ELF — синтетическая фикстура."""
from contextlib import contextmanager
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import tomllib
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/backend"))

from thorfg.config import defaults, migrate_settings, parse_config, render, validate_profile
from thorfg.paths import Paths, ThorError
from thorfg.runtime import (LIBRARY, MANIFEST, LAYER, Runtimes, SOURCES, elf,
                            inspect_bundle, layer_conflicts, sha256)
from thorfg.service import Service
from thorfg.steam import Steam, vdf
from thorfg.storage import Store, atomic, json_bytes, read_bytes

spec = importlib.util.spec_from_file_location("decky_installer", ROOT / "scripts/decky_plugin.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Base(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "user"
        self.home.mkdir()
        self.paths = Paths(self.home)
        self.service = Service(self.paths)

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode() if isinstance(value, str) else value)
        return path

    def bundle(self, machine=183, commit=None):
        directory = self.root / "bundle"
        directory.mkdir(exist_ok=True)
        header = bytearray(128)
        header[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HH", header, 16, 3, machine)
        self.put(directory / LIBRARY, header)
        self.put(directory / "UPSTREAM-LICENSE", "Synthetic fixture: not a real runtime")
        self.put(directory / MANIFEST, json_bytes({"file_format_version": "1.1.0", "layer": {
            "name": LAYER, "type": "GLOBAL", "api_version": "1.4.328", "implementation_version": "2",
            "library_path": LIBRARY, "disable_environment": {"DISABLE_LSFGVK": "1"}}}))
        report = {"commit": commit or next(iter(SOURCES)), "version": "v2.0.0-dev",
                  "adapter": "historical-2dev", "architecture": "aarch64", "patches": [],
                  "sha256": {name: sha256((directory / name).read_bytes()) for name in (LIBRARY, MANIFEST, "UPSTREAM-LICENSE")}}
        self.put(directory / "build-report.json", json_bytes(report))
        return directory

    def game(self, appid="42", name="Тестовая игра", library=None):
        library = library or self.home / ".local/share/Steam"
        directory = library / "steamapps/common" / name
        directory.mkdir(parents=True, exist_ok=True)
        app = f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{name}" }}'
        self.put(library / "steamapps" / f"appmanifest_{appid}.acf", app)
        return directory

    @contextmanager
    def arm(self):
        with patch("thorfg.service.platform.system", return_value="Linux"), \
                patch("thorfg.service.platform.machine", return_value="aarch64"):
            yield


class ConfigurationTests(Base):
    def test_roundtrip_keeps_unknown_fields_and_comments(self):
        raw = b'version=2\n# user comment\n[global]\ncustom="keep"\n[[profile]]\nname="Other"\nactive_in="Other.exe"\nunknown=17\n'
        result = render(raw, {"42": {"enabled": True, "process": "Game.exe"}})
        parsed = tomllib.loads(result.decode())
        self.assertIn(b"# user comment", result)
        self.assertEqual(parsed["global"]["custom"], "keep")
        self.assertEqual(parsed["profile"][0]["unknown"], 17)

    def test_managed_unknown_fields_survive(self):
        raw = b'version=2\n[global]\n[[profile]]\nname="ThorFG:42"\nactive_in=["Game.exe"]\ncustom=9\n'
        result = render(raw, {"42": {"enabled": True, "process": "Game.exe", "multiplier": 3}})
        self.assertEqual(tomllib.loads(result.decode())["profile"][0]["custom"], 9)

    def test_disable_keeps_unmanaged(self):
        raw = render(None, {"42": {"enabled": True, "process": "Game.exe"}})
        result = render(raw, {"42": {"enabled": False}})
        self.assertEqual(tomllib.loads(result.decode())["profile"], [])

    def test_corrupt_toml_refused(self):
        with self.assertRaises(ThorError):
            parse_config(b"[[profile]\n")

    def test_old_version_refused(self):
        with self.assertRaises(ThorError):
            parse_config(b"version=1")

    def test_semantically_invalid_config_refused(self):
        for value in (b'version=2\n[[profile]]\nmultiplier=0',
                      b'version=2\n[[profile]]\nflow_scale=nan',
                      b'version=2\n[global]\ndll=17'):
            with self.subTest(value=value), self.assertRaises(ThorError):
                parse_config(value)

    def test_overlap_and_duplicates_refused(self):
        with self.assertRaises(ThorError):
            render(None, {"42": {"enabled": True, "process": "Game.exe"},
                          "43": {"enabled": True, "process": "bin/Game.exe"}})

    def test_unmanaged_target_conflict(self):
        with self.assertRaises(ThorError):
            render(b'version=2\n[[profile]]\nactive_in="Game.exe"', {"42": {"enabled": True, "process": "Game.exe"}})

    def test_multiline_toml_is_not_split_on_fake_header(self):
        raw = b'version=2\n[global]\nnote="""\n[[profile]]\ntext\n"""\n'
        self.assertIn("[[profile]]", tomllib.loads(render(raw, {}).decode())["global"]["note"])

    def test_stable_rejects_legacy_gpu(self):
        raw = b'version=2\n[global]\n[[profile]]\nname="Other"\ngpu="old"'
        with self.assertRaises(ThorError):
            render(raw, {}, "stable-2.0")

    def test_bad_profile_types_and_ranges(self):
        for value in ({"multiplier": True}, {"multiplier": 5}, {"flow_scale": float("nan")},
                      {"flow_scale": .1}, {"enabled": "yes"}, {"runtime": "../../etc"},
                      {"enabled": True, "process": "../Game.exe"}, {"process": "bad\nname"}):
            with self.subTest(value=value), self.assertRaises(ThorError):
                validate_profile("42", value)

    def test_disabled_profile_kept_without_runtime(self):
        self.service.save_profile("42", {"process": "Game.exe"})
        self.assertEqual(self.service.settings()["profiles"]["42"]["process"], "Game.exe")
        self.assertFalse(self.paths.config.exists())

    def test_migrate_settings(self):
        settings = migrate_settings({"profiles": {"42": {"process": "Game.exe"}}})
        self.assertEqual(settings["schema_version"], 1)
        self.assertFalse(settings["profiles"]["42"]["enabled"])

    def test_future_settings_rejected(self):
        with self.assertRaises(ThorError):
            migrate_settings({"schema_version": 99, "profiles": {}})


class StorageTests(Base):
    def test_backup_and_rollback(self):
        self.put(self.paths.config, "original")
        store = Store(self.paths)
        with store.lock():
            store.apply({self.paths.config: b"new", self.paths.settings: b"settings"})
        self.assertTrue(list((self.paths.state / "history").glob("*.json")))
        store.rollback()
        self.assertEqual(self.paths.config.read_bytes(), b"original")
        self.assertFalse(self.paths.settings.exists())

    def test_rollback_external_change_refused(self):
        store = Store(self.paths)
        with store.lock():
            store.apply({self.paths.config: b"new"})
        self.put(self.paths.config, b"external")
        with self.assertRaises(ThorError):
            store.rollback()
        self.assertEqual(self.paths.config.read_bytes(), b"external")

    def test_optimistic_concurrency(self):
        self.put(self.paths.config, b"external")
        store = Store(self.paths)
        with store.lock(), self.assertRaises(ThorError):
            store.apply({self.paths.config: b"new"}, expected={self.paths.config: b"old"})

    def test_cooperative_lock(self):
        store = Store(self.paths)
        with store.lock():
            with self.assertRaises(ThorError):
                with Store(self.paths).lock():
                    pass

    def test_atomic_failure_restores_multiple_files(self):
        self.put(self.paths.config, b"before")
        real_atomic = atomic
        def failing(path, value, paths):
            if path == self.paths.settings and value == b"new settings":
                raise OSError("fault injection")
            return real_atomic(path, value, paths)
        store = Store(self.paths)
        with store.lock(), patch("thorfg.storage.atomic", side_effect=failing), self.assertRaises(OSError):
            store.apply({self.paths.config: b"after", self.paths.settings: b"new settings"})
        self.assertEqual(self.paths.config.read_bytes(), b"before")
        self.assertFalse(store.pending.exists())

    def test_post_replace_failure_restores_current_file(self):
        real_atomic = atomic
        def failing(path, value, paths):
            real_atomic(path, value, paths)
            if path == self.paths.config and value == b"new":
                raise OSError("fsync failed after rename")
        store = Store(self.paths)
        with store.lock(), patch("thorfg.storage.atomic", side_effect=failing), self.assertRaises(OSError):
            store.apply({self.paths.config: b"new"})
        self.assertFalse(self.paths.config.exists())

    def test_crash_journal_recovery(self):
        from thorfg.storage import encode
        record = {"id": "crashed", "kind": "configuration", "rolled_back": False,
                  "entries": [{"path": str(self.paths.config.relative_to(self.home)),
                               "before": encode(b"old"), "after": encode(b"new")}]}
        self.put(self.paths.config, b"new")
        self.put(self.paths.state / "pending.json", json_bytes(record))
        with self.assertRaises(ThorError):
            with Store(self.paths).lock():
                pass
        Store(self.paths).rollback()
        self.assertEqual(self.paths.config.read_bytes(), b"old")

    def test_path_escape_refused(self):
        with self.assertRaises(ThorError):
            atomic(self.root / "outside", b"bad", self.paths)
        with self.assertRaises(ThorError):
            atomic(self.home / "sub/../conf", b"bad", self.paths)

    def test_journal_cannot_touch_game_saves(self):
        path = self.put(self.home / "game/save.dat", "precious")
        with Store(self.paths).lock(), self.assertRaises(ThorError):
            Store(self.paths).apply({path: None})
        self.assertEqual(path.read_text(), "precious")

    def test_symlink_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.home / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows не разрешает symlink для этого пользователя")
        with self.assertRaises(ThorError):
            atomic(link / "file", b"bad", self.paths)


class SteamTests(Base):
    def test_multiple_libraries_and_unicode(self):
        self.game()
        library = self.root / "card"
        self.game("43", "Другая игра", library)
        value = str(library).replace("\\", "\\\\")
        self.put(self.home / ".local/share/Steam/steamapps/libraryfolders.vdf",
                 f'"libraryfolders" {{ "0" {{ "path" "{value}" }} }}')
        self.assertEqual(len(Steam(self.home).games()), 2)

    def test_corrupt_manifest_skipped(self):
        self.game()
        self.put(self.home / ".local/share/Steam/steamapps/appmanifest_43.acf", '"AppState" {')
        steam = Steam(self.home)
        self.assertEqual(len(steam.games()), 1)
        self.assertTrue(steam.warnings)

    def test_unsafe_installdir_skipped(self):
        self.put(self.home / ".local/share/Steam/steamapps/appmanifest_42.acf",
                 '"AppState" { "appid" "42" "name" "bad" "installdir" "../../escape" }')
        self.assertEqual(Steam(self.home).games(), [])

    def test_executables_include_launcher_and_actual_game(self):
        directory = self.game()
        self.put(directory / "Launcher.exe", "fixture")
        self.put(directory / "Binaries/Win64/RealGame.EXE", "fixture")
        self.assertEqual(Steam(self.home).executables("42"), ["Launcher.exe", "Binaries/Win64/RealGame.EXE"])

    def test_missing_game_error(self):
        with self.assertRaises(ThorError):
            Steam(self.home).executables("99")

    def test_vdf_comments_escapes_and_duplicate_keys(self):
        self.assertEqual(vdf('// c\n"a" "b\\\\c"')["a"], "b\\c")
        with self.assertRaises(ThorError):
            vdf('"a" "b" "a" "c"')

    def test_dll_missing_and_discovered(self):
        self.assertIsNone(Steam(self.home).dll())
        directory = self.game("993090", "Lossless Scaling")
        self.put(directory / "Lossless.dll", "fixture")
        self.assertIsNotNone(Steam(self.home).dll())
        self.assertIsNone(Steam(self.home).dll(modern=True))


class RuntimeTests(Base):
    def test_valid_elf(self):
        self.assertEqual(elf(self.bundle() / LIBRARY), "aarch64")

    def test_wrong_architecture(self):
        with self.assertRaises(ThorError):
            inspect_bundle(self.bundle(machine=62))

    def test_truncated_elf(self):
        path = self.put(self.root / "bad.so", b"\x7fELF")
        with self.assertRaises(ThorError):
            elf(path)

    def test_checksum_mismatch(self):
        directory = self.bundle()
        self.put(directory / LIBRARY, b"tampered")
        with self.assertRaises(ThorError):
            inspect_bundle(directory)

    def test_unknown_revision(self):
        with self.assertRaises(ThorError):
            inspect_bundle(self.bundle(commit="a" * 40))

    def test_manifest_missing(self):
        directory = self.bundle()
        (directory / MANIFEST).unlink()
        with self.assertRaises(ThorError):
            inspect_bundle(directory)

    def test_install_activate_switch_rollback_uninstall(self):
        runtimes = Runtimes(self.paths)
        runtimes.import_bundle(self.bundle(), "candidate")
        self.assertEqual(runtimes.list()[0]["slot"], "candidate")
        self.service.activate("candidate")
        self.assertEqual(runtimes.active()["slot"], "candidate")
        self.service.uninstall_runtime()
        self.assertIsNone(runtimes.active())
        self.service.store.rollback()
        self.assertEqual(runtimes.active()["slot"], "candidate")

    def test_slot_not_overwritten(self):
        directory = self.bundle()
        self.service.runtimes.import_bundle(directory, "candidate")
        with self.assertRaises(ThorError):
            self.service.runtimes.import_bundle(directory, "candidate")

    def test_foreign_layer_blocks_activation(self):
        self.service.runtimes.import_bundle(self.bundle(), "candidate")
        foreign = self.paths.manifest.with_name("Other.json")
        self.put(foreign, json_bytes({"layer": {"name": LAYER}}))
        with self.assertRaises(ThorError):
            self.service.activate("candidate")
        self.assertTrue(foreign.exists())

    def test_manager_conflict_blocks_config_not_read(self):
        self.put(self.paths.decky_root / "plugins/Other/plugin.json", '{"name":"Armada LSFG"}')
        self.assertFalse(self.service.status()["hardware_verified"])
        with self.assertRaises(ThorError):
            self.service.save_profile("42", {})
        with self.assertRaises(ThorError):
            self.service.rollback()

    def test_mako_is_only_reported(self):
        path = self.paths.manifest.with_name("mako.json")
        self.put(path, '{"layer":{"name":"MAKO"}}')
        conflicts, tools = layer_conflicts(self.paths)
        self.assertFalse(conflicts)
        self.assertIn(str(path), tools)
        self.assertTrue(path.exists())

    def test_enable_requires_dll_and_valid_runtime(self):
        with self.arm(), self.assertRaises(ThorError):
            self.service.save_profile("42", {"enabled": True, "process": "Game.exe"})
        self.service.runtimes.import_bundle(self.bundle(), "candidate")
        self.service.activate("candidate")
        with self.arm(), self.assertRaises(ThorError):
            self.service.save_profile("42", {"enabled": True, "process": "Game.exe", "runtime": "candidate"})

    def test_save_enable_disable_and_restore(self):
        self.service.runtimes.import_bundle(self.bundle(), "candidate")
        self.service.activate("candidate")
        self.put(self.game("993090", "Lossless Scaling") / "Lossless.dll", "fixture")
        self.game()
        with self.arm():
            self.service.save_profile("42", {"enabled": True, "process": "Game.exe", "runtime": "candidate"})
        self.assertEqual(tomllib.loads(self.paths.config.read_text("utf-8"))["profile"][0]["multiplier"], 2)
        self.service.save_profile("42", {"enabled": False, "process": "Game.exe", "runtime": "candidate"})
        self.assertEqual(tomllib.loads(self.paths.config.read_text("utf-8"))["profile"], [])
        self.assertEqual(self.service.settings()["profiles"]["42"]["process"], "Game.exe")

    def test_external_config_override_blocks_write(self):
        with patch.dict("os.environ", {"LSFGVK_CONFIG": "/external/config.toml"}), self.assertRaises(ThorError):
            self.service.save_profile("42", {})

    def test_disable_works_with_broken_runtime(self):
        self.service.runtimes.import_bundle(self.bundle(), "candidate")
        self.service.activate("candidate")
        self.put(self.game("993090", "Lossless Scaling") / "Lossless.dll", "fixture")
        with self.arm():
            self.service.save_profile("42", {"enabled": True, "process": "Game.exe", "runtime": "candidate"})
        self.put(self.paths.runtimes / "candidate" / LIBRARY, b"broken")
        self.service.save_profile("42", {"enabled": False, "process": "Game.exe", "runtime": "candidate"})
        self.assertEqual(tomllib.loads(self.paths.config.read_text("utf-8"))["profile"], [])

    def test_export_contains_no_user_paths_or_profile_data(self):
        self.service.save_profile("42", {"process": "SecretToken.exe"})
        with patch.object(self.service, "probe_vulkan", return_value={"available": False, "listed": None, "gpu": None, "driver": None}):
            output = Path(self.service.export()).read_text("utf-8")
        self.assertNotIn(str(self.home), output)
        self.assertNotIn("SecretToken", output)
        self.assertNotIn("profiles\"", output)
        self.assertIn('"hardware_verified": false', output)


class PluginInstallerTests(Base):
    def package(self, evil=False):
        name = "../escape" if evil else "plugin.json"
        files = {name: b'{"name":"ThorFG"}'}
        metadata = {"name": "ThorFG", "files": {key: sha256(value) for key, value in files.items()}}
        path = self.root / "package.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in files.items():
                archive.writestr("ThorFG/" + key, value)
            archive.writestr("ThorFG/thorfg-package.json", json_bytes(metadata))
        return path

    def test_install_and_uninstall_preserves_other_plugin(self):
        other = self.put(self.paths.decky_root / "plugins/Other/data.txt", "precious")
        installer.deploy(self.paths, self.package())
        target = self.paths.decky_root / "plugins/ThorFG/plugin.json"
        self.assertTrue(target.exists())
        installer.deploy(self.paths, uninstall=True)
        self.assertFalse(target.exists())
        self.assertEqual(other.read_text(), "precious")
        Store(self.paths).rollback()
        self.assertTrue(target.exists())

    def test_zip_traversal_refused(self):
        with self.assertRaises(ThorError):
            installer.deploy(self.paths, self.package(evil=True))

    def test_existing_unowned_directory_refused(self):
        self.put(self.paths.decky_root / "plugins/ThorFG/local.txt", "keep")
        with self.assertRaises(ThorError):
            installer.deploy(self.paths, self.package())

    def test_modified_plugin_file_preserved(self):
        package = self.package()
        installer.deploy(self.paths, package)
        path = self.put(self.paths.decky_root / "plugins/ThorFG/plugin.json", "local edit")
        with self.assertRaises(ThorError):
            installer.deploy(self.paths, package)
        self.assertEqual(path.read_text(), "local edit")


class DeckyContractTests(Base):
    def test_async_rpc_contract_and_errors(self):
        # Явный test stub вместо модуля, предоставляемого реальным Decky Loader.
        stub = SimpleNamespace(DECKY_USER_HOME=str(self.home), DECKY_HOME=str(self.paths.decky_root),
                               logger=logging.getLogger("thorfg-test"))
        stub.logger.addHandler(logging.NullHandler())
        with patch.dict(sys.modules, {"decky": stub}):
            spec = importlib.util.spec_from_file_location("thorfg_plugin_test", ROOT / "plugin/main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin = module.Plugin()
            async def exercise():
                await plugin._main()
                status = await plugin.get_status()
                self.assertTrue(status["ok"])
                self.assertFalse(status["data"]["hardware_verified"])
                error = await plugin.get_executables("999")
                self.assertFalse(error["ok"])
                self.assertIsInstance(error["error"], str)
                await plugin._unload()
            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
