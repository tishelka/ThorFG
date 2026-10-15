import { callable } from "@decky/api";

type Reply<T> = { ok: true; data: T } | { ok: false; error: string };
export async function unwrap<T>(reply: Promise<Reply<T>>): Promise<T> {
  const value = await reply;
  if (!value.ok) throw new Error(value.error);
  return value.data;
}
export type Profile = {
  enabled: boolean; multiplier: number; flow_scale: number; performance_mode: boolean;
  process: string; runtime: string;
};
export type Runtime = { slot: string; integrity?: boolean; version?: string; architecture?: string };
export type Status = {
  stage: string; hardware_verified: false; host_architecture: string; dll_found: boolean;
  game_count: number; profile_count: number;
  runtime: (Runtime & { adapter: string; commit: string }) | null;
  checks: { id: string; state: "ok" | "unknown" | "error"; message: string }[];
  vulkan: { listed: boolean | null; gpu: string | null; driver: string | null };
  settings: { active_runtime: string | null; profiles: Record<string, Profile> };
  runtimes: Runtime[]; warnings: string[];
};
export type Game = { appid: string; name: string; install_dir: string };
export type Process = { pid: number; executables: string[]; layer_mapped: boolean };
export const rpc = {
  status: callable<[probe: boolean], Reply<Status>>("get_status"),
  games: callable<[], Reply<{ games: Game[]; warnings: string[] }>>("get_games"),
  executables: callable<[appid: string], Reply<string[]>>("get_executables"),
  save: callable<[appid: string, profile: Profile], Reply<Profile>>("save_profile"),
  export: callable<[], Reply<string>>("export_diagnostics"),
  processes: callable<[], Reply<Process[]>>("get_processes"),
  importProfiles: callable<[], Reply<number>>("import_profiles"),
  importRuntime: callable<[directory: string, slot: string], Reply<string>>("import_runtime"),
  activate: callable<[slot: string], Reply<string>>("activate_runtime"),
  rollback: callable<[], Reply<string>>("rollback"),
};
