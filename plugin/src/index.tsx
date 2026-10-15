import {
  ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, SliderField,
  TextField, ToggleField, staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { useEffect, useState } from "react";
import { FaBolt } from "react-icons/fa";
import { Game, Process, Profile, Status, rpc, unwrap } from "./api";
import { Key, Language, translate } from "./i18n";

const initial = (runtime: string): Profile => ({ enabled: false, multiplier: 2, flow_scale: .5,
  performance_mode: true, process: "", runtime });

function Content() {
  const [language, setLanguage] = useState<Language>("ru");
  const t = (key: Key) => translate(language, key);
  const [page, setPage] = useState("overview");
  const [status, setStatus] = useState<Status>();
  const [games, setGames] = useState<Game[]>([]);
  const [appid, setAppid] = useState("");
  const [profile, setProfile] = useState<Profile>(initial("historical"));
  const [exes, setExes] = useState<string[]>([]);
  const [processes, setProcesses] = useState<Process[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [directory, setDirectory] = useState("");
  const [slot, setSlot] = useState("historical");
  const [selectedSlot, setSelectedSlot] = useState("");
  const [confirm, setConfirm] = useState(false);

  const refresh = async (probe = false) => {
    const next = await unwrap(rpc.status(probe));
    setStatus(next);
    setGames((await unwrap(rpc.games())).games);
  };
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("backendError")); }
    finally { setBusy(false); }
  };
  useEffect(() => { void run(() => refresh()); }, []);
  const selectGame = (id: string) => {
    setAppid(id); setExes([]); setDirty(false); setNotice("");
    setProfile(status?.settings.profiles[id] ?? initial(status?.runtime?.slot ?? "historical"));
  };
  const change = (patch: Partial<Profile>) => { setProfile({ ...profile, ...patch }); setDirty(true); };
  const row = (label: string, value: string) => <PanelSectionRow key={label}>
    <Field label={label}><span style={{ color: "#dbeafe", overflowWrap: "anywhere" }}>{value}</span></Field>
  </PanelSectionRow>;
  const runtimeOptions = status?.runtimes.filter(r => r.integrity).map(r => ({
    data: r.slot, label: `${r.slot} · ${r.version}`,
  })) ?? [];
  const canConfigure = !!status?.runtime;
  const checkNames: Record<string, Key> = { architecture: "arch", settings: "settings", config: "config",
    runtime: "runtime", dll: "dll", backend: "backend", transaction: "transaction", tools: "tools",
    loader: "loader", manager_conflict: "managerConflict", layer_conflict: "layerConflict",
    games: "games", overrides: "overrides", armada: "armada" };

  return <div style={{ color: "#e5edf7", paddingBottom: 12 }}>
    <PanelSection>
      <PanelSectionRow><DropdownItem label={t("page")} selectedOption={page} disabled={busy}
        rgOptions={(["overview", "games", "diagnostics", "runtime"] as const).map(key => ({ data: key, label: t(key) }))}
        onChange={option => { setPage(option.data as string); setConfirm(false); }} /></PanelSectionRow>
      <PanelSectionRow><DropdownItem label={t("language")} selectedOption={language}
        rgOptions={[{ data: "ru", label: "Русский" }, { data: "en", label: "English" }]}
        onChange={option => setLanguage(option.data as Language)} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void run(() => refresh())}>
        {busy ? t("loading") : t("refresh")}</ButtonItem></PanelSectionRow>
      {error && <PanelSectionRow><div role="alert" style={{ padding: "10px 0", color: "#fca5a5", whiteSpace: "pre-wrap" }}>{error}</div></PanelSectionRow>}
      {notice && <PanelSectionRow><div role="status" style={{ padding: "10px 0", color: "#a7f3d0", overflowWrap: "anywhere" }}>{notice}</div></PanelSectionRow>}
    </PanelSection>
    {page === "overview" && <PanelSection title="ThorFG">
      <PanelSectionRow><div style={{ padding: "8px 0 14px", color: "#fcd34d" }}>● {t("disclaimer")}</div></PanelSectionRow>
      {row(t("stage"), status ? status.stage === "Configuration Verified" ? status.stage : t("needsCheck") : t("unknown"))}
      {row(t("version"), status?.runtime?.version ?? t("absent"))}
      {row(t("arch"), status?.runtime?.architecture ?? status?.host_architecture ?? t("unknown"))}
      {row("Vulkan Layer", status?.vulkan.listed == null ? t("unknown") : t(status.vulkan.listed ? "found" : "absent"))}
      {row("Lossless Scaling DLL", t(status?.dll_found ? "found" : "absent"))}
      {row(t("gpu"), status?.vulkan.gpu ?? t("unknown"))}
      {row(t("driver"), status?.vulkan.driver ?? t("unknown"))}
      {row(t("profiles"), status ? `${status.profile_count} / ${status.game_count}` : t("unknown"))}
    </PanelSection>}
    {page === "games" && <>
      <PanelSection title={t("games")}>
        <PanelSectionRow><DropdownItem label={t("chooseGame")} selectedOption={appid} disabled={busy || !games.length}
          strDefaultLabel={t("chooseGame")} rgOptions={games.map(g => ({ data: g.appid, label: g.name }))}
          onChange={option => selectGame(option.data as string)} /></PanelSectionRow>
        {!games.length && row(t("games"), t("noGames"))}
      </PanelSection>
      {appid && <PanelSection title={`${t("profiles")} · ${appid}`}>
        <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
          setExes(await unwrap(rpc.executables(appid)));
        })}>{t("scanExe")}</ButtonItem></PanelSectionRow>
        {!!exes.length && <PanelSectionRow><DropdownItem label={t("chooseExe")} selectedOption={profile.process}
          disabled={busy} rgOptions={exes.map(exe => ({ data: exe, label: exe }))}
          onChange={option => change({ process: option.data as string })} /></PanelSectionRow>}
        <PanelSectionRow><TextField label={t("process")} description={t("processHint")} value={profile.process}
          disabled={busy} onChange={event => change({ process: event.target.value })} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label={t("enabled")} description={t("disableHint")} checked={profile.enabled}
          disabled={busy || (!canConfigure && !profile.enabled)} onChange={enabled => change({ enabled })} /></PanelSectionRow>
        <PanelSectionRow><DropdownItem label={t("selectRuntime")} selectedOption={profile.runtime}
          disabled={busy || !runtimeOptions.length} rgOptions={runtimeOptions}
          onChange={option => change({ runtime: option.data as string })} /></PanelSectionRow>
        <PanelSectionRow><DropdownItem label={t("multiplier")} selectedOption={profile.multiplier}
          disabled={busy || !canConfigure} rgOptions={[2, 3, 4].map(data => ({ data, label: `×${data}` }))}
          onChange={option => change({ multiplier: option.data as number })} /></PanelSectionRow>
        <PanelSectionRow><SliderField label={t("scale")} value={profile.flow_scale} min={.25} max={1} step={.05}
          showValue disabled={busy || !canConfigure} onChange={flow_scale => change({ flow_scale })} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label={t("performance")} checked={profile.performance_mode}
          disabled={busy || !canConfigure} onChange={performance_mode => change({ performance_mode })} /></PanelSectionRow>
        {row(t("stage"), dirty ? t("draft") : status?.settings.profiles[appid]?.enabled ? t("applied") : t("inactive"))}
        {!canConfigure && row(t("runtime"), t("noRuntime"))}
        <PanelSectionRow><ButtonItem disabled={busy || !dirty} onClick={() => void run(async () => {
          await unwrap(rpc.save(appid, profile)); setDirty(false); await refresh(); setNotice(t("savedHint"));
        })}>{t("save")}</ButtonItem></PanelSectionRow>
      </PanelSection>}
    </>}
    {page === "diagnostics" && <PanelSection title={t("health")}>
      {status?.checks.map(check => <PanelSectionRow key={check.id}><Field label={t(checkNames[check.id] ?? "health")}
        description={language === "ru" ? check.message : t(check.state === "ok" ? "verified" : check.state === "error" ? "needsCheck" : "unknown")}><span style={{ color: check.state === "ok" ? "#a7f3d0" : check.state === "error" ? "#fca5a5" : "#fcd34d" }}>
          {check.state === "ok" ? "✓" : check.state === "error" ? "!" : "?"}</span></Field></PanelSectionRow>)}
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(() => refresh(true))}>{t("probe")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
        setNotice(`${t("exported")}: ${await unwrap(rpc.export())}`);
      })}>{t("export")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
        setProcesses(await unwrap(rpc.processes()));
      })}>{t("processes")}</ButtonItem></PanelSectionRow>
      {processes?.length === 0 && row(t("processes"), t("noProcesses"))}
      {processes?.map(p => row(`PID ${p.pid}`, `${p.executables.join(", ")} · ${t(p.layer_mapped ? "mapped" : "unmapped")}`))}
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
        const count = await unwrap(rpc.importProfiles()); await refresh(); setNotice(`${t("imported")}: ${count}`);
      })}>{t("importProfiles")}</ButtonItem></PanelSectionRow>
    </PanelSection>}
    {page === "runtime" && <PanelSection title={t("runtime")}>
      {row(t("activeRuntime"), status?.runtime?.slot ?? t("absent"))}
      <PanelSectionRow><Field description={t("localOnly")} /></PanelSectionRow>
      <PanelSectionRow><TextField label={t("bundle")} value={directory} disabled={busy}
        onChange={event => setDirectory(event.target.value)} /></PanelSectionRow>
      <PanelSectionRow><TextField label={t("slot")} value={slot} disabled={busy}
        onChange={event => setSlot(event.target.value)} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !directory || !slot} onClick={() => void run(async () => {
        await unwrap(rpc.importRuntime(directory, slot)); await refresh(); setNotice(t("success"));
      })}>{t("importRuntime")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><DropdownItem label={t("runtime")} selectedOption={selectedSlot} disabled={busy || !runtimeOptions.length}
        rgOptions={runtimeOptions} onChange={option => setSelectedSlot(option.data as string)} /></PanelSectionRow>
      <PanelSectionRow><Field description={t("rollbackHint")} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !selectedSlot} onClick={() => void run(async () => {
        await unwrap(rpc.activate(selectedSlot)); await refresh(); setNotice(t("success"));
      })}>{t("activate")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => {
        if (!confirm) { setConfirm(true); return; }
        setConfirm(false); void run(async () => { await unwrap(rpc.rollback()); await refresh(); setNotice(t("success")); });
      }}>{t(confirm ? "confirmRollback" : "rollback")}</ButtonItem></PanelSectionRow>
    </PanelSection>}
  </div>;
}

export default definePlugin(() => ({
  name: "ThorFG", titleView: <div className={staticClasses.Title}>ThorFG</div>,
  content: <Content />, icon: <FaBolt />, onDismount() {},
}));
