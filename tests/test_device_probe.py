import json
from pathlib import Path
import struct
import shutil
import subprocess
import os
import sys
from unittest.mock import patch

from test_thorfg import Base
from thorfg.bundle import LIBRARY, MANIFEST, LAYER
from thorfg.diagnostics import DeviceProbe, analyze_vulkan, isolated_environment
from thorfg.elf import elf_info
from thorfg.paths import ThorError


class ProbeTests(Base):
    def native(self):
        fixture = self.bundle()
        directory = self.home / "thorfg/.build/historical/build-llvm/lsfg-vk-layer"
        for name in (LIBRARY, MANIFEST):
            self.put(directory / name, (fixture / name).read_bytes())
        return directory / LIBRARY

    def foreign(self, bits, machine, name):
        header = bytearray(64)
        header[:7] = b"\x7fELF" + bytes([2 if bits == 64 else 1, 1, 1])
        struct.pack_into("<HH", header, 16, 3, machine)
        library = self.put(self.home / ".local/lib" / (name + ".so"), header)
        self.put(self.paths.manifest.with_name(name + ".json"), json.dumps({"layer": {"name": LAYER, "library_path": str(library)}}))

    def snapshot(self):
        return {p.relative_to(self.home): p.read_bytes() if p.is_file() else None for p in self.home.rglob("*")}

    def test_read_only_detects_foreign_architectures_and_native_build(self):
        self.native()
        self.foreign(64, 62, "lsfg64")
        self.foreign(32, 3, "lsfg32")
        for name in ("ArmadaLSFG", "Decky LSFG-VK"):
            self.put(self.paths.decky_root / "plugins" / name / "plugin.json", json.dumps({"name": name}))
        before = self.snapshot()
        with self.arm(), patch("thorfg.diagnostics.subprocess.run", side_effect=AssertionError("passive diagnostics must not execute tools")):
            result = DeviceProbe(self.paths).scan()
            status = self.service.status()
        self.assertTrue(result["read_only"])
        self.assertTrue(result["local_build_found"])
        self.assertFalse(result["slot_installed"])
        self.assertFalse(result["runtime_activated"])
        self.assertEqual({p["architecture"] for p in result["external_layers"]}, {"x86_64", "i386"})
        self.assertEqual(set(result["external_managers"]), {"ArmadaLSFG", "Decky LSFG-VK"})
        self.assertFalse(status["lifecycle"]["profiles_writable"])
        self.assertEqual(before, self.snapshot())

    def test_foreign_layers_block_writes_and_activation(self):
        self.foreign(64, 62, "lsfg64")
        self.service.runtimes.import_bundle(self.bundle(), "candidate")
        before = self.paths.manifest.with_name("lsfg64.json").read_bytes()
        with self.assertRaises(ThorError):
            self.service.activate("candidate")
        with self.assertRaises(ThorError):
            self.service.save_profile("42", {})
        self.assertEqual(self.paths.manifest.with_name("lsfg64.json").read_bytes(), before)
        self.assertFalse(self.paths.config.exists())

    def test_loader_logs_are_not_fg_or_runtime_initialization(self):
        stderr = f'lsfg-vk: using profile with name \'(environment)\'\nInsert instance layer "{LAYER}"\nInserted device layer "{LAYER}"\nfailed to get device proc addr for vkCreateSwapchainKHR (error -3)'
        result = analyze_vulkan("deviceName = Turnip Adreno (TM) 740\ndriverName = turnip", stderr, 1)
        self.assertTrue(result["layer_inserted"])
        self.assertTrue(result["swapchain_query_warning"])
        self.assertIsNone(result["runtime_initialized"])
        self.assertFalse(result["fg_actually_verified"])
        self.assertEqual(result["gpu"], "Turnip Adreno (TM) 740")

    def test_child_environment_does_not_mutate_parent(self):
        with patch.dict("os.environ", {"VK_INSTANCE_LAYERS": "FOREIGN", "LSFGVK_CONFIG": "/foreign", "LD_PRELOAD": "foreign.so"}):
            env = isolated_environment(self.root, self.root / "implicit", self.root / "own.so")
            import os
            self.assertEqual(os.environ["VK_INSTANCE_LAYERS"], "FOREIGN")
            self.assertNotIn("VK_INSTANCE_LAYERS", env)
            self.assertNotIn("LD_PRELOAD", env)
            self.assertEqual(env["LSFGVK_ENV"], "1")
            self.assertNotEqual(env["LSFGVK_CONFIG"], "/foreign")

    def test_loader_probe_uses_only_temporary_manifest_and_config(self):
        self.native()
        original = self.put(self.paths.config, "user config must stay untouched")
        seen = {}
        def execute(args, **kwargs):
            env = kwargs["env"]
            manifest = Path(env["VK_IMPLICIT_LAYER_PATH"]) / "ThorFG-test.json"
            seen["directory"] = manifest.parent.parent
            self.assertTrue(manifest.is_file())
            self.assertNotEqual(env["LSFGVK_CONFIG"], str(original))
            return subprocess.CompletedProcess(args, 1, "deviceName = Turnip\n", f'Inserted device layer "{LAYER}"')
        with self.arm(), patch("os.geteuid", return_value=1000, create=True), patch("thorfg.diagnostics.shutil.which", return_value="/usr/bin/vulkaninfo"), \
                patch("thorfg.diagnostics.subprocess.run", side_effect=execute):
            result = DeviceProbe(self.paths).run("loader")
        self.assertFalse(result["layer_inserted"])  # Instance insertion was not observed.
        self.assertFalse(seen["directory"].exists())
        self.assertEqual(original.read_text(), "user config must stay untouched")

    def test_native_host_load_is_explicit_and_timeout_is_not_success(self):
        self.native()
        with self.arm(), patch("os.geteuid", return_value=1000, create=True), \
                patch("thorfg.diagnostics.subprocess.run", side_effect=subprocess.TimeoutExpired(["python"], 1)):
            result = DeviceProbe(self.paths).run("host-load", timeout=1)
        self.assertFalse(result["host_load_verified"])
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["fg_actually_verified"])

    def test_arbitrary_rpc_mode_is_refused(self):
        with self.assertRaises(ThorError):
            self.service.device_probe("cube")

    def test_check_dry_run_diagnose_cli_do_not_write_to_home(self):
        root = Path(__file__).resolve().parents[1]
        # На Thor сам checkout тоже внутри HOME. Проверяем и скрытые import cache,
        # а не только настройки вне каталога разработки.
        project = self.home / "thorfg"
        shutil.copytree(root / "plugin/backend", project / "plugin/backend",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for script in ("thorfg.py", "device_probe.py"):
            self.put(project / "scripts" / script, (root / "scripts" / script).read_bytes())
        before = self.snapshot()
        for mode in ("check", "dry-run", "diagnose"):
            result = subprocess.run([sys.executable, str(project / "scripts/thorfg.py"), mode],
                                    capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, str(project / "scripts/device_probe.py")],
                                capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_foreign_library_is_not_silently_replaced_by_native_candidate(self):
        self.native()
        foreign = self.bundle(machine=62) / LIBRARY
        self.assertIsNone(DeviceProbe(self.paths).scan(foreign)["native_runtime"])
        with self.arm(), patch("os.geteuid", return_value=1000, create=True), self.assertRaises(ThorError):
            DeviceProbe(self.paths).run("host-load", library=foreign)

    def test_export_does_not_start_vulkan(self):
        with patch.object(self.service, "probe_vulkan", side_effect=AssertionError("export must not start Vulkan")):
            self.service.export()

    def test_host_load_uses_isolated_child_environment(self):
        self.native()
        def execute(args, **kwargs):
            env = kwargs["env"]
            self.assertNotIn("LD_PRELOAD", env)
            self.assertNotEqual(env["LSFGVK_CONFIG"], str(self.paths.config))
            self.assertTrue(Path(env["LSFGVK_CONFIG"]).is_file())
            return subprocess.CompletedProcess(args, 0, "THORFG_HOST_LOAD_OK\n", "")
        with self.arm(), patch("os.geteuid", return_value=1000, create=True), \
                patch.dict(os.environ, {"LD_PRELOAD": "foreign.so", "LSFGVK_CONFIG": str(self.paths.config)}), \
                patch("thorfg.diagnostics.subprocess.run", side_effect=execute):
            self.assertTrue(DeviceProbe(self.paths).run("host-load")["host_load_verified"])

    def test_explicit_bad_elf_version_is_not_verified(self):
        path = self.native()
        data = bytearray(path.read_bytes())
        data[6] = 0
        path.write_bytes(data)
        self.assertIsNone(DeviceProbe(self.paths).scan(path)["native_runtime"])

    def test_error_mention_of_layer_name_is_not_discovery(self):
        result = analyze_vulkan("", f"ERROR loading {LAYER}", 1)
        self.assertFalse(result["layer_discovered"])

    def test_cli_help_is_utf8_even_with_legacy_windows_output_encoding(self):
        root = Path(__file__).resolve().parents[1]
        for script in ("runtime/build.py", "scripts/device_probe.py", "scripts/thorfg.py"):
            result = subprocess.run([sys.executable, str(root / script), "--help"],
                                    capture_output=True, encoding="utf-8", timeout=20,
                                    env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)

    def test_probe_evidence_is_merged_for_one_binary_hash(self):
        digest = "a" * 64
        with patch("thorfg.service.DeviceProbe.run", side_effect=[
                {"mode": "host-load", "library_sha256": digest, "host_load_verified": True, "fg_actually_verified": False},
                {"mode": "loader", "library_sha256": digest, "host_load_verified": None, "layer_inserted": True, "fg_actually_verified": False}]):
            self.service.device_probe("host-load")
            result = self.service.device_probe("loader")
        self.assertTrue(result["host_load_verified"])
        self.assertTrue(result["layer_inserted"])
        self.assertFalse(result["fg_actually_verified"])
