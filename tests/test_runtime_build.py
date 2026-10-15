"""Build tests use local Git fixtures, synthetic ELF and mocked tool output; no compilation."""
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from test_thorfg import Base

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import build as builder
from runtime.source import acquire, load_source, verify_checkout
from runtime.toolchain import TOOLS, cmake_arguments, discover_tools, validate_cache
from runtime.packaging import package_existing
from thorfg.bundle import LIBRARY, MANIFEST, inspect_bundle, sha256, verify_sums
from thorfg.paths import ThorError


class BuilderTests(Base):
    def setUp(self):
        super().setUp()
        # Захватываем сообщения synthetic build, не выдаём их за реальную сборку.
        output = patch("sys.stdout", new_callable=io.StringIO)
        self.output = output.start()
        self.addCleanup(output.stop)

    def source(self):
        return load_source(ROOT, "historical")

    def cache(self, checkout, build, bad=None):
        entries = {"CMAKE_HOME_DIRECTORY": str(checkout), "CMAKE_GENERATOR": "Ninja",
                   "CMAKE_BUILD_TYPE": "Release", "CMAKE_INTERPROCEDURAL_OPTIMIZATION": "ON",
                   "CMAKE_CACHE_MAJOR_VERSION": "4", "CMAKE_CACHE_MINOR_VERSION": "3", "CMAKE_CACHE_PATCH_VERSION": "0"}
        for key, tool in (("CMAKE_AR", "llvm-ar"), ("CMAKE_RANLIB", "llvm-ranlib"),
                          ("CMAKE_CXX_COMPILER_AR", "llvm-ar"), ("CMAKE_CXX_COMPILER_RANLIB", "llvm-ranlib")):
            entries[key] = "/usr/bin/" + tool
        if bad:
            entries[bad] = bad + "-NOTFOUND"
        self.put(build / "CMakeCache.txt", "\n".join(f"{key}:STRING={value}" for key, value in entries.items()))
        self.put(build / "build.ninja", "# fixture, not a real build")
        self.put(build / ".ninja_log", "# ninja log v5\n0\t1\t1\tlsfg-vk-layer/liblsfg-vk-layer.so\thash\n")
        self.put(build / "CMakeFiles/4.3.0/CMakeCXXCompiler.cmake",
                 'set(CMAKE_CXX_COMPILER_ID "Clang")\nset(CMAKE_CXX_COMPILER_VERSION "22.1.8")\n')

    def prepared(self):
        source = self.source()
        project = self.home / "thorfg"
        checkout = project / ".build/historical"
        build = checkout / "build-llvm"
        self.cache(checkout, build)
        fixture = self.bundle()
        for name in (LIBRARY, MANIFEST):
            self.put(build / "lsfg-vk-layer" / name, (fixture / name).read_bytes())
        self.put(checkout / "LICENSE.md", "Synthetic test license")
        self.put(project / "runtime/sources.lock.json", (ROOT / "runtime/sources.lock.json").read_bytes())
        return project, checkout, build, source

    def tool_output(self, *args):
        if args[0].endswith("nm"):
            return "0000 T vkNegotiateLoaderLayerInterfaceVersion"
        return "Mock tool observation, not a real ARM64 build"

    def test_sources_have_exact_verified_tree_and_separate_adapters(self):
        historical, stable = self.source(), load_source(ROOT, "stable")
        self.assertEqual(historical["tree"], "8e35469d1977b8640b44bb88f122a53f7f21eb41")
        self.assertIn("https://github.com/eugeniosegala/lsfg-vk-experimental.git", historical["mirrors"])
        self.assertNotEqual(historical["adapter"], stable["adapter"])

    def test_untrusted_mirror_in_lockfile_rejected(self):
        data = json.loads((ROOT / "runtime/sources.lock.json").read_text("utf-8"))
        data["historical"]["mirrors"].append("https://example.invalid/fake.git")
        self.put(self.root / "runtime/sources.lock.json", json.dumps(data))
        with self.assertRaises(ThorError):
            load_source(self.root, "historical")

    def test_missing_llvm_tools_fail_before_cmake(self):
        for missing in ("llvm-ar", "llvm-ranlib"):
            with self.subTest(missing=missing), patch("runtime.toolchain.shutil.which", side_effect=lambda name: None if name == missing else "/usr/bin/" + name):
                with self.assertRaisesRegex(ThorError, missing):
                    discover_tools()

    def test_cmake_sets_all_llvm_archiver_options(self):
        tools = {name: "/usr/bin/" + name for name in TOOLS}
        args = cmake_arguments(Path("src"), Path("build"), tools)
        for key in ("CMAKE_AR", "CMAKE_CXX_COMPILER_AR"):
            self.assertIn("-D" + key + "=/usr/bin/llvm-ar", args)
        for key in ("CMAKE_RANLIB", "CMAKE_CXX_COMPILER_RANLIB"):
            self.assertIn("-D" + key + "=/usr/bin/llvm-ranlib", args)

    def test_bad_cache_is_not_deleted_or_repaired_silently(self):
        project, checkout, build, _ = self.prepared()
        self.cache(checkout, build, "CMAKE_CXX_COMPILER_AR")
        before = (build / "CMakeCache.txt").read_bytes()
        with self.assertRaisesRegex(ThorError, "NOTFOUND|cache"):
            validate_cache(checkout, build)
        self.assertEqual((build / "CMakeCache.txt").read_bytes(), before)
        self.assertTrue((build / "lsfg-vk-layer" / LIBRARY).is_file())

    def test_cache_requires_source_and_completed_ninja_metadata(self):
        _, checkout, build, _ = self.prepared()
        with self.assertRaises(ThorError):
            validate_cache(self.root / "other", build, completed=True)
        (build / ".ninja_log").unlink()
        with self.assertRaises(ThorError):
            validate_cache(checkout, build, completed=True)

    def test_package_manual_build_without_recompiling(self):
        project, checkout, build, source = self.prepared()
        digest = sha256((build / "lsfg-vk-layer" / LIBRARY).read_bytes())
        before = {p: p.read_bytes() for p in build.rglob("*") if p.is_file()}
        tools = {name: "/usr/bin/" + name for name in TOOLS}
        verified = {"source_repository": source["mirrors"][0], "source_tree": source["tree"], "commit": source["commit"]}
        with patch("runtime.packaging.verify_checkout", return_value=verified), patch("runtime.packaging.output", side_effect=self.tool_output):
            report = package_existing(project, checkout, build, project / "artifacts/runtime/historical", source, tools, digest)
        bundle = project / "artifacts/runtime/historical"
        inspected, _ = inspect_bundle(bundle)
        self.assertEqual(inspected["source_repository"], source["mirrors"][0])
        self.assertEqual(report["build_evidence"]["compiler_version_recorded"], "22.1.8")
        self.assertEqual(report["build_evidence"]["mode"], "recovered")
        self.assertFalse(report["hardware_verified"])
        self.assertIn("build-report.json", verify_sums(bundle))
        self.assertEqual(before, {p: p.read_bytes() for p in build.rglob("*") if p.is_file()})
        self.service.runtimes.import_bundle(bundle, "recovered")
        self.assertTrue(self.service.runtimes.list()[0]["integrity"])
        # SHA256SUMS защищает и provenance JSON, а не только .so.
        self.put(bundle / "build-report.json", (bundle / "build-report.json").read_bytes() + b" ")
        with self.assertRaises(ThorError):
            inspect_bundle(bundle)

    def test_no_provenance_record_or_wrong_sha_refused(self):
        project, checkout, build, source = self.prepared()
        with patch("runtime.packaging.verify_checkout", return_value={}), self.assertRaises(ThorError):
            package_existing(project, checkout, build, project / "out", source, {}, None)
        with patch("runtime.packaging.verify_checkout", return_value={}), self.assertRaises(ThorError):
            package_existing(project, checkout, build, project / "out", source, {}, "0" * 64)
        self.assertFalse((project / "out").exists())

    def test_package_cli_path_never_calls_build_dnf_or_acquire(self):
        project, checkout, build, source = self.prepared()
        tools = {name: "/usr/bin/" + name for name in TOOLS}
        args = ["--package-existing", "--use-existing-checkout", str(checkout), "--build-dir", str(build),
                "--expected-sha256", sha256((build / "lsfg-vk-layer" / LIBRARY).read_bytes())]
        verified = {"source_repository": source["repository"], "source_tree": source["tree"], "commit": source["commit"]}
        with self.arm(), patch.object(builder, "ROOT", project), patch("runtime.build.discover_tools", return_value=tools), \
                patch("runtime.build.run", side_effect=AssertionError("unexpected build/installation")), \
                patch("runtime.build.acquire", side_effect=AssertionError("unexpected clone")), \
                patch("runtime.packaging.verify_checkout", return_value=verified), \
                patch("runtime.packaging.output", side_effect=self.tool_output):
            self.assertEqual(builder.main(args), 0)

    def test_package_refuses_existing_destination(self):
        project, checkout, build, source = self.prepared()
        destination = project / "out"
        self.put(destination / "keep", "precious")
        with self.assertRaises(ThorError):
            package_existing(project, checkout, build, destination, source, {}, "0" * 64)
        self.assertEqual((destination / "keep").read_text(), "precious")

    def test_mirror_fallback_keeps_failed_checkout(self):
        source = self.source()
        target = self.home / "thorfg/.build/historical"
        attempted = []
        def clone(args, **kwargs):
            candidate = Path(args[-1])
            candidate.mkdir()
            self.put(candidate / "partial", "kept")
            attempted.append(args[-2])
            if len(attempted) == 1:
                raise subprocess.TimeoutExpired(args, 300)
            return subprocess.CompletedProcess(args, 0)
        with patch("runtime.source.subprocess.run", side_effect=clone), patch("runtime.source.git"), patch("runtime.source.verify_checkout"):
            acquired = acquire(self.home, source, target)
        self.assertEqual(attempted, [source["repository"], source["mirrors"][0]])
        self.assertEqual(acquired, target)
        self.assertEqual(len(list(target.parent.glob("fetch-*/partial"))), 1)


class SourceCheckoutTests(Base):
    def setUp(self):
        super().setUp()
        self.checkout = self.home / "source"
        self.checkout.mkdir()
        self.git("init", "-b", "develop")
        self.put(self.checkout / "source.cpp", "// fixture\n")
        self.git("add", "source.cpp")
        self.git("-c", "user.name=ThorFG Test", "-c", "user.email=test@example.invalid", "commit", "--no-gpg-sign", "-m", "fixture")
        self.git("remote", "add", "origin", "https://github.com/eugeniosegala/lsfg-vk-experimental.git")
        self.source = {"commit": self.git("rev-parse", "HEAD"), "tree": self.git("rev-parse", "HEAD^{tree}"), "adapter": "historical-2dev"}

    def git(self, *args):
        return subprocess.run(["git", "-c", "safe.directory=" + str(self.checkout), "-C", str(self.checkout), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_exact_checkout_and_mirror_pass(self):
        result = verify_checkout(self.checkout, self.source)
        self.assertTrue(result["tracked_clean"])

    def test_wrong_commit_and_tree_refused(self):
        for key in ("commit", "tree"):
            with self.subTest(key=key), self.assertRaises(ThorError):
                verify_checkout(self.checkout, {**self.source, key: "0" * 40})

    def test_dirty_tracked_checkout_refused(self):
        self.put(self.checkout / "source.cpp", "changed")
        with self.assertRaises(ThorError):
            verify_checkout(self.checkout, self.source)

    def test_only_selected_build_untracked_files_are_allowed(self):
        build = self.checkout / "build-llvm"
        self.put(build / "result", "fixture")
        verify_checkout(self.checkout, self.source, build)
        self.put(self.checkout / "unexpected.cpp", "source change")
        with self.assertRaises(ThorError):
            verify_checkout(self.checkout, self.source, build)
