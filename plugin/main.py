"""Decky загружает этот файл; управление системой остаётся в backend/thorfg."""
import asyncio
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_root / "py_modules"))
sys.path.insert(0, str(_root / "backend"))

import decky
from thorfg.paths import Paths
from thorfg.service import Service


class Plugin:
    async def _main(self):
        self.service = Service(Paths.environment(Path(decky.DECKY_USER_HOME), Path(decky.DECKY_HOME)))
        self._operation = asyncio.Lock()

    async def _call(self, name, *args):
        try:
            async with self._operation:
                result = await asyncio.to_thread(getattr(self.service, name), *args)
            return {"ok": True, "data": result}
        except Exception as exc:
            decky.logger.exception("Ошибка ThorFG: %s", name)
            return {"ok": False, "error": str(exc)}

    async def get_status(self, probe=False):
        return await self._call("status", probe)

    async def get_games(self):
        return await self._call("games")

    async def get_executables(self, appid):
        return await self._call("executables", appid)

    async def save_profile(self, appid, profile):
        return await self._call("save_profile", appid, profile)

    async def activate_runtime(self, slot):
        return await self._call("activate", slot)

    async def import_runtime(self, directory, slot):
        # Локальная операция; никаких URL, shell или удалённого выполнения.
        async with self._operation:
            try:
                result = await asyncio.to_thread(self.service.runtimes.import_bundle, Path(directory), slot)
                return {"ok": True, "data": result}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

    async def import_profiles(self):
        return await self._call("import_profiles")

    async def export_diagnostics(self):
        return await self._call("export")

    async def get_processes(self):
        return await self._call("processes")

    async def probe_runtime(self, mode="check"):
        return await self._call("device_probe", mode)

    async def rollback(self):
        return await self._call("rollback")

    async def _unload(self):
        pass
