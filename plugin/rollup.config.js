import { nodeResolve } from "@rollup/plugin-node-resolve";
import replace from "@rollup/plugin-replace";
import typescript from "@rollup/plugin-typescript";
import externalGlobals from "rollup-plugin-external-globals";
import { readFileSync } from "node:fs";

const manifest = JSON.parse(readFileSync(new URL("./plugin.json", import.meta.url), "utf8"));

// Globals — контракт загрузчика Decky, сверенный с @decky/rollup 1.0.2.
// Preset не используется: его delete/glob dependency tree имеет незакрытый advisory.
export default {
  input: "src/index.tsx",
  context: "window",
  external: ["react", "react-dom", "@decky/ui"],
  plugins: [
    typescript(),
    nodeResolve({ browser: true }),
    externalGlobals({ react: "SP_REACT", "react/jsx-runtime": "SP_JSX",
      "react-dom": "SP_REACTDOM", "@decky/ui": "DFL", "@decky/manifest": JSON.stringify(manifest) }),
    replace({ preventAssignment: true, "process.env.NODE_ENV": JSON.stringify("production") }),
  ],
  output: { file: "dist/index.js", format: "esm", exports: "default", sourcemap: false },
};
