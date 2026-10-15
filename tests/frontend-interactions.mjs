// Render the shipped bundle with real React/DOM. Decky controls and RPC are test
// doubles: these tests verify ThorFG onClick/state wiring, not Steam's input stack.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, afterEach, beforeEach, test } from "node:test";

const require = createRequire(new URL("../plugin/package.json", import.meta.url));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = require("react");
const { act, createElement: h } = React;
const { createRoot } = require("react-dom/client");
globalThis.SP_REACT = React;
globalThis.SP_JSX = require("react/jsx-runtime");

const field = ({ label, description, children }) => h("div", { "data-field": label }, label, description, children);
globalThis.DFL = {
  staticClasses: { Title: "test-title" },
  PanelSection: ({ title, children }) => h("section", { "data-section": title }, title && h("h2", null, title), children),
  PanelSectionRow: ({ children }) => h("div", null, children),
  Field: field,
  ButtonItem: ({ label, description, children, disabled, onClick }) => h("div", null, label,
    h("button", { type: "button", "data-button-label": label, disabled, onClick }, children), description),
  TextField: ({ label, value, disabled, onChange }) => h("label", null, label,
    h("input", { "data-field-label": label, value, disabled, onChange })),
  ToggleField: ({ label, checked, disabled, onChange }) => h("label", null, label,
    h("input", { type: "checkbox", checked, disabled, onChange: event => onChange(event.target.checked) })),
  SliderField: ({ label, value, disabled }) => h("input", { "aria-label": label, type: "range", value, disabled, readOnly: true }),
  get DropdownItem() { throw new Error("ThorFG must not depend on DropdownItem"); },
};

let fixture, calls, root, container, originalStatus;
window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit = {
  connect() {
    return { _version: 2, callable: method => async (...args) => {
      calls.push({ method, args });
      if (method === "get_status") {
        if (fixture.statusWait) await fixture.statusWait;
        return { ok: true, data: fixture.status };
      }
      if (method === "get_games") return { ok: true, data: { games: fixture.games, warnings: [] } };
      if (method === "get_executables") return { ok: true, data: fixture.exes };
      throw new Error("Unexpected side-effect RPC: " + method);
    } };
  },
};
const { default: plugin } = await import("../plugin/dist/index.js");

function makeFixture() {
  return {
    games: Array.from({ length: 237 }, (_, i) => ({ appid: String(i), name: `Game ${String(i).padStart(3, "0")}`, install_dir: "/fixture" })),
    exes: Array.from({ length: 65 }, (_, i) => `candidate-${String(i).padStart(3, "0")}.exe`),
    status: {
      stage: "Configuration Verified", hardware_verified: false, host_architecture: "aarch64",
      runtime: { slot: "historical", version: "v2.0.0-dev", architecture: "aarch64" },
      checks: [], vulkan: { listed: null, gpu: null, driver: null }, dll_found: false,
      game_count: 237, profile_count: 1, warnings: [],
      settings: { active_runtime: "historical", profiles: {
        "37": { enabled: false, multiplier: 3, flow_scale: .5, performance_mode: true, process: "saved.exe", runtime: "historical" },
      } },
      runtimes: [
        { slot: "historical", version: "v2.0.0-dev", integrity: true },
        { slot: "stable", version: "2.0.0", integrity: true },
        { slot: "broken", version: "unknown", integrity: false },
      ],
      lifecycle: {
        read_only: false, profiles_writable: true, activation_allowed: true,
        profile_write_block_reasons: [], write_block_reasons: [], runtime_activated: true,
        slot_installed: true, local_build_found: true, local_bundle_found: true,
        native_runtime: null, external_managers: [], external_layers: [], last_probe: null,
      },
    },
  };
}

beforeEach(() => {
  fixture = makeFixture(); calls = [];
  container = document.createElement("div"); document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount()); container.remove();
  // Navigation and local draft selection must never save/activate/run Vulkan.
  assert.ok(calls.every(call => ["get_status", "get_games", "get_executables"].includes(call.method)), JSON.stringify(calls));
  assert.ok(calls.filter(call => call.method === "get_status").every(call => call.args[0] === false));
  assert.deepEqual(fixture.status, originalStatus, "RPC profile objects must not be mutated by UI selections");
});
after(() => dom.window.close());

async function mount() {
  originalStatus = structuredClone(fixture.status);
  await act(async () => root.render(plugin().content));
  assert.equal(container.querySelector('[role="alert"]'), null);
  assert.equal(container.querySelectorAll("select").length, 0);
}
const text = node => node.textContent.replace(/\s+/g, " ").trim();
function button(caption) {
  const result = [...container.querySelectorAll("button")].find(node => text(node) === caption);
  assert.ok(result, `Missing button: ${caption}`);
  return result;
}
function labelledButton(label) {
  const result = [...container.querySelectorAll("button")].find(node => node.dataset.buttonLabel === label);
  assert.ok(result, `Missing labelled button: ${label}`);
  return result;
}
async function click(target) {
  await act(async () => (typeof target === "string" ? button(target) : target).click());
}
async function search(value) {
  const input = container.querySelector('input[data-field-label="Поиск по списку"]');
  assert.ok(input);
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}
async function selectGame(id = "0") {
  await click(labelledButton("Раздел"));
  await click(labelledButton("Выберите игру"));
  await search(`Game ${id.padStart(3, "0")} · ${id}`);
  await click(`Game ${id.padStart(3, "0")} · ${id}`);
}

test("section buttons cycle through real React state and language toggles without resetting the section", async () => {
  await mount();
  for (const expected of ["Обзор", "Игры", "Диагностика", "Runtime", "Обзор"]) {
    assert.equal(text(labelledButton("Раздел")), expected);
    await click(labelledButton("Раздел"));
  }
  assert.equal(text(labelledButton("Раздел")), "Игры");
  await click(labelledButton("Язык"));
  assert.equal(text(labelledButton("Language")), "English");
  assert.equal(text(labelledButton("Section")), "Games");
  await click(labelledButton("Language"));
  assert.equal(text(labelledButton("Язык")), "Русский");
  // Functional state updates must also survive two activations before a render.
  await act(async () => { labelledButton("Раздел").click(); labelledButton("Раздел").click(); });
  assert.equal(text(labelledButton("Раздел")), "Runtime");
});

test("237 games use individual paged buttons; selecting a later game restores its saved draft", async () => {
  await mount();
  await click(labelledButton("Раздел"));
  await click(labelledButton("Выберите игру"));
  const gameButtons = () => [...container.querySelectorAll("button")].filter(node => /^Game \d/.test(text(node)));
  assert.equal(gameButtons().length, 20);
  assert.equal(button("Предыдущие варианты").disabled, true);
  assert.equal(gameButtons().at(-1).textContent, "Game 019 · 19");
  await click("Следующие варианты");
  assert.equal(text(gameButtons()[0]), "Game 020 · 20");
  await click("Предыдущие варианты");
  assert.equal(text(gameButtons()[0]), "Game 000 · 0");
  await click("Следующие варианты");
  await click("Game 037 · 37");
  assert.equal(text(labelledButton("Выберите игру")), "Game 037");
  assert.equal(container.querySelector('input[data-field-label="Целевой процесс"]').value, "saved.exe");
  assert.equal(text(labelledButton("Множитель")), "×3");
  assert.equal(button("Сохранить профиль").disabled, true);
});

test("search selects the last game, supports no matches and clear/back without changing the selection", async () => {
  await mount();
  await selectGame("236");
  await click(labelledButton("Выберите игру"));
  await search("GAME 236");
  assert.ok(button("✓ Game 236 · 236"));
  await search("missing game");
  assert.match(container.textContent, /Совпадений нет/);
  await click("Сбросить поиск");
  assert.ok(button("Game 000 · 0"));
  await click("Назад к разделу");
  assert.equal(text(labelledButton("Выберите игру")), "Game 236");
});

test("EXE/runtime/multiplier buttons change local profile state, and slot choice does not activate", async () => {
  await mount(); await selectGame();
  await click("Найти исполняемые файлы");
  assert.ok(button("candidate-000.exe"));
  await search("candidate-064"); await click("candidate-064.exe");
  assert.equal(container.querySelector('input[data-field-label="Целевой процесс"]').value, "candidate-064.exe");
  assert.equal(calls.find(call => call.method === "get_executables").args[0], "0");
  await click(labelledButton("Runtime профиля"));
  assert.equal(container.textContent.includes("broken · unknown"), false);
  await click("stable · 2.0.0");
  assert.equal(text(labelledButton("Runtime профиля")), "stable · 2.0.0");
  for (const expected of ["×3", "×4", "×2"]) {
    await click(labelledButton("Множитель"));
    assert.equal(text(labelledButton("Множитель")), expected);
  }
  assert.match(container.textContent, /Есть несохранённые изменения/);
  assert.equal(button("Сохранить профиль").disabled, false);
  await click(labelledButton("Раздел")); await click(labelledButton("Раздел"));
  assert.equal(button("Активировать выбранный runtime").disabled, true);
  await click(labelledButton("Runtime")); await click("stable · 2.0.0");
  assert.equal(text(labelledButton("Runtime")), "stable · 2.0.0");
  assert.equal(button("Активировать выбранный runtime").disabled, false);
});

test("read-only status keeps multiplier/save/activation blocked while navigation and slot browsing work", async () => {
  Object.assign(fixture.status.lifecycle, { read_only: true, profiles_writable: false, activation_allowed: false,
    profile_write_block_reasons: ["External LSFG"] });
  await mount(); await selectGame();
  const multiplier = labelledButton("Множитель");
  assert.equal(multiplier.disabled, true);
  await click(multiplier);
  assert.equal(text(labelledButton("Множитель")), "×2");
  assert.equal(button("Сохранить профиль").disabled, true);
  await click(labelledButton("Раздел")); await click(labelledButton("Раздел"));
  await click(labelledButton("Runtime")); await click("stable · 2.0.0");
  assert.equal(button("Активировать выбранный runtime").disabled, true);
  await click("Активировать выбранный runtime");
});

test("switching sections closes an open picker; empty libraries disable game choice", async () => {
  fixture.games = []; await mount();
  await click(labelledButton("Раздел"));
  assert.equal(labelledButton("Выберите игру").disabled, true);
  assert.match(container.textContent, /Установленные Steam-игры не найдены/);
  await click(labelledButton("Раздел")); await click(labelledButton("Раздел"));
  await click(labelledButton("Runtime"));
  assert.ok(button("Назад к разделу"));
  await click(labelledButton("Раздел"));
  assert.equal(text(labelledButton("Раздел")), "Обзор");
  assert.equal(container.textContent.includes("Назад к разделу"), false);
});

test("refresh disables navigation while RPC is pending and restores the button handlers afterwards", async () => {
  await mount();
  let release;
  fixture.statusWait = new Promise(resolve => { release = resolve; });
  await click("Обновить");
  assert.equal(labelledButton("Раздел").disabled, true);
  assert.equal(labelledButton("Язык").disabled, true);
  await click(labelledButton("Раздел"));
  assert.equal(text(labelledButton("Раздел")), "Обзор");
  await act(async () => release());
  assert.equal(labelledButton("Раздел").disabled, false);
  await click(labelledButton("Раздел"));
  assert.equal(text(labelledButton("Раздел")), "Игры");
  assert.equal(calls.filter(call => call.method === "get_status").length, 2);
});
