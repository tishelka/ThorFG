#!/usr/bin/env python3
"""Короткая удалённая диагностика. По умолчанию не запускает Vulkan и не пишет файлы."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/py_modules"))
sys.path.insert(0, str(ROOT / "plugin/backend"))
from thorfg.paths import Paths, ThorError
from thorfg.diagnostics import DeviceProbe


def main(argv=None):
    parser = argparse.ArgumentParser(description="ThorFG: чтение сведений или явный ограниченный тест")
    parser.add_argument("--mode", choices=["check", "host-load", "summary", "loader", "cube"], default="check")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--wayland-display")
    args = parser.parse_args(argv)
    try:
        result = DeviceProbe(Paths.environment(), ROOT).run(args.mode, library=args.library,
                   expected_sha=args.expected_sha256, timeout=args.timeout, wayland_display=args.wayland_display)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.mode == "host-load" and not result.get("host_load_verified"):
            return 1
        return 0
    except (OSError, ValueError, ThorError, TypeError) as exc:
        print("Диагностика остановлена:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
