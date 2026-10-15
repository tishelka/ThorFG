// Проверка итогового JS с явными mock globals; не заменяет запуск в Decky.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Итоговый Decky-модуль загружается и использует существующие backend RPC", async () => {
  const calls = [];
  globalThis.window = {
    __DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit: {
      connect(version, name) {
        assert.equal(version, 2);
        assert.equal(name, "ThorFG");
        return { _version: 2, callable(method) { calls.push(method); return () => {}; } };
      },
    },
  };
  globalThis.SP_REACT = { createContext: value => ({ value }) };
  globalThis.SP_JSX = { jsx: (type, props) => ({ type, props }) };
  globalThis.DFL = { staticClasses: { Title: "test-title" } };
  const module = await import("../plugin/dist/index.js");
  const plugin = module.default();
  assert.equal(plugin.name, "ThorFG");
  assert.equal(typeof plugin.onDismount, "function");
  assert.ok(plugin.content && plugin.titleView && plugin.icon);
  const backend = await readFile(new URL("../plugin/main.py", import.meta.url), "utf8");
  for (const method of calls) assert.match(backend, new RegExp(`async def ${method}\\(`));
  assert.ok(calls.length >= 10);
});
