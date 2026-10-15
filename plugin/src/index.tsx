import {
  ButtonItem, Field, PanelSection, PanelSectionRow, SliderField,
  TextField, ToggleField, staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { useEffect, useState } from "react";
import { FaBolt } from "react-icons/fa";
import { Game, Process, Profile, Status, rpc, unwrap } from "./api";
import { Key, Language, translate } from "./i18n";
import { SelectionList } from "./SelectionList";

const pages = ["overview", "games", "diagnostics", "runtime"] as const;
type Page = typeof pages[number];
type Picker = "game" | "exe" | "profileRuntime" | "runtimeSlot";
const multipliers = [2, 3, 4];

const initial = (runtime: string): Profile => ({ enabled: false, multiplier: 2, flow_scale: .5,
  performance_mode: true, process: "", runtime });

function Content() {
  const [language, setLanguage] = useState<Language>("ru");
  const t = (key: Key) => translate(language, key);
  const [page, setPage] = useState<Page>("overview");
  const [picker, setPicker] = useState<Picker | null>(null);
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
  const change = (patch: Partial<Profile>) => { setProfile(current => ({ ...current, ...patch })); setDirty(true); };
  const row = (label: string, value: string) => <PanelSectionRow key={label}>
    <Field label={label}><span style={{ color: "#dbeafe", overflowWrap: "anywhere" }}>{value}</span></Field>
  </PanelSectionRow>;
  const runtimeOptions = status?.runtimes.filter(r => r.integrity).map(r => ({
    data: r.slot, label: `${r.slot} · ${r.version}`,
  })) ?? [];
  const pickerOptions = picker === "game" ? games.map(game => ({ value: game.appid, label: `${game.name} · ${game.appid}` }))
    : picker === "exe" ? exes.map(exe => ({ value: exe, label: exe }))
    : runtimeOptions.map(option => ({ value: option.data, label: option.label }));
  const pickerTitle = t(picker === "game" ? "chooseGame" : picker === "exe" ? "chooseExe"
    : picker === "profileRuntime" ? "selectRuntime" : "runtime");
  const pickerValue = picker === "game" ? appid : picker === "exe" ? profile.process
    : picker === "profileRuntime" ? profile.runtime : selectedSlot;
  const choose = (value: string) => {
    if (picker === "game") selectGame(value);
    else if (picker === "exe") change({ process: value });
    else if (picker === "profileRuntime") change({ runtime: value });
    else if (picker === "runtimeSlot") setSelectedSlot(value);
    setPicker(null);
  };
  const canConfigure = !!status?.lifecycle.profiles_writable;
  const lifecycle = status?.lifecycle;
  const probe = lifecycle?.last_probe;
  const layerDiscovered = status?.vulkan.listed ?? probe?.layer_discovered;
  const evidence = (value?: boolean | null) => value === true ? t("verified") : value === false ? t("needsCheck") : t("unknown");
  const lifecycleView = <>
    {row(t("localBuild"), t(lifecycle?.local_build_found ? "found" : "absent"))}
    {row(t("localBundle"), t(lifecycle?.local_bundle_found ? "found" : "absent"))}
    {row(t("slotInstalled"), t(lifecycle?.slot_installed ? "found" : "absent"))}
    {row(t("activated"), t(lifecycle?.runtime_activated ? "found" : "absent"))}
    {row(t("arch"), lifecycle?.native_runtime?.architecture ?? t("unknown"))}
    {row(t("elfVerified"), evidence(lifecycle?.native_runtime?.elf_verified))}
    {row(t("externalManagers"), lifecycle?.external_managers.join(", ") || t("absent"))}
    {row(t("externalLayers"), lifecycle?.external_layers.map(layer => layer.architecture).join(" / ") || t("absent"))}
    {row(t("coexistence"), lifecycle ? t(lifecycle.read_only ? "readOnly" : "noExternal") : t("unknown"))}
    {!canConfigure && <PanelSectionRow><Field label={t("blocked")}
      description={lifecycle?.profile_write_block_reasons.join(". ")} /></PanelSectionRow>}
    {row(t("hostLoaded"), evidence(probe?.host_load_verified))}
    {row(t("layerDiscovered"), evidence(probe?.layer_discovered))}
    {row(t("layerInserted"), evidence(probe?.layer_inserted))}
    {row(t("runtimeInit"), evidence(probe?.runtime_initialized))}
    <PanelSectionRow><Field description={t("gamePending")} /></PanelSectionRow>
  </>;
  const checkNames: Record<string, Key> = { architecture: "arch", settings: "settings", config: "config",
    runtime: "runtime", dll: "dll", backend: "backend", transaction: "transaction", tools: "tools",
    loader: "loader", manager_conflict: "managerConflict", layer_conflict: "layerConflict",
    games: "games", overrides: "overrides", armada: "armada" };

  return <div style={{ color: "#e5edf7", paddingBottom: 12 }}>
    <PanelSection>
      <PanelSectionRow><ButtonItem label={t("page")} disabled={busy}
        description={`${t("nextSection")}: ${t(pages[(pages.indexOf(page) + 1) % pages.length])}`}
        onClick={() => { setPage(current => pages[(pages.indexOf(current) + 1) % pages.length]); setPicker(null); setConfirm(false); }}>
        {t(page)}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem label={t("language")} disabled={busy}
        onClick={() => setLanguage(current => current === "ru" ? "en" : "ru")}>
        {language === "ru" ? "Русский" : "English"}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void run(() => refresh())}>
        {busy ? t("loading") : t("refresh")}</ButtonItem></PanelSectionRow>
      {error && <PanelSectionRow><div role="alert" style={{ padding: "10px 0", color: "#fca5a5", whiteSpace: "pre-wrap" }}>{error}</div></PanelSectionRow>}
      {notice && <PanelSectionRow><div role="status" style={{ padding: "10px 0", color: "#a7f3d0", overflowWrap: "anywhere" }}>{notice}</div></PanelSectionRow>}
    </PanelSection>
    {picker ? <SelectionList key={picker} title={pickerTitle} options={pickerOptions} selected={pickerValue}
      disabled={busy} t={t} onSelect={choose} onClose={() => setPicker(null)} /> : <>
    {page === "overview" && <PanelSection title="ThorFG">
      <PanelSectionRow><div style={{ padding: "8px 0 14px", color: "#fcd34d" }}>● {t("disclaimer")}</div></PanelSectionRow>
      {row(t("stage"), status ? status.stage === "Configuration Verified" ? status.stage : t("needsCheck") : t("unknown"))}
      {row(t("version"), status?.runtime?.version ?? t("absent"))}
      {row(t("arch"), status?.runtime?.architecture ?? status?.host_architecture ?? t("unknown"))}
      {row("Vulkan Layer", layerDiscovered == null ? t("unknown") : t(layerDiscovered ? "found" : "absent"))}
      {row("Lossless Scaling DLL", t(status?.dll_found ? "found" : "absent"))}
      {row(t("gpu"), status?.vulkan.gpu ?? probe?.gpu ?? t("unknown"))}
      {row(t("driver"), status?.vulkan.driver ?? probe?.driver ?? t("unknown"))}
      {row(t("profiles"), status ? `${status.profile_count} / ${status.game_count}` : t("unknown"))}
    </PanelSection>}
    {page === "games" && <>
      <PanelSection title={t("games")}>
        <PanelSectionRow><ButtonItem label={t("chooseGame")} layout="below" disabled={busy || !games.length}
          onClick={() => setPicker("game")}>
          {games.find(game => game.appid === appid)?.name ?? t("chooseGame")}</ButtonItem></PanelSectionRow>
        {!games.length && row(t("games"), t("noGames"))}
      </PanelSection>
      {appid && <PanelSection title={`${t("profiles")} · ${appid}`}>
        <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
          const candidates = await unwrap(rpc.executables(appid));
          setExes(candidates);
          if (candidates.length) setPicker("exe");
        })}>{t("scanExe")}</ButtonItem></PanelSectionRow>
        {!!exes.length && <PanelSectionRow><ButtonItem label={t("chooseExe")} layout="below" disabled={busy}
          onClick={() => setPicker("exe")}>
          {profile.process || t("chooseExe")}</ButtonItem></PanelSectionRow>}
        <PanelSectionRow><TextField label={t("process")} description={t("processHint")} value={profile.process}
          disabled={busy} onChange={event => change({ process: event.target.value })} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label={t("enabled")} description={t("disableHint")} checked={profile.enabled}
          disabled={busy || (!canConfigure && !profile.enabled)} onChange={enabled => change({ enabled })} /></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={t("selectRuntime")} layout="below" disabled={busy || !runtimeOptions.length}
          onClick={() => setPicker("profileRuntime")}>
          {runtimeOptions.find(option => option.data === profile.runtime)?.label ?? profile.runtime}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={t("multiplier")} disabled={busy || !canConfigure} onClick={() => {
          setProfile(current => ({ ...current, multiplier: multipliers[(multipliers.indexOf(current.multiplier) + 1) % multipliers.length] }));
          setDirty(true);
        }}>×{profile.multiplier}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><SliderField label={t("scale")} value={profile.flow_scale} min={.25} max={1} step={.05}
          showValue disabled={busy || !canConfigure} onChange={flow_scale => change({ flow_scale })} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label={t("performance")} checked={profile.performance_mode}
          disabled={busy || !canConfigure} onChange={performance_mode => change({ performance_mode })} /></PanelSectionRow>
        {row(t("stage"), dirty ? t("draft") : status?.settings.profiles[appid]?.enabled ? t("applied") : t("inactive"))}
        {!canConfigure && <PanelSectionRow><Field label={t("blocked")}
          description={lifecycle?.profile_write_block_reasons.join(". ")} /></PanelSectionRow>}
        <PanelSectionRow><ButtonItem disabled={busy || !dirty || !canConfigure} onClick={() => void run(async () => {
          await unwrap(rpc.save(appid, profile)); setDirty(false); await refresh(); setNotice(t("savedHint"));
        })}>{t("save")}</ButtonItem></PanelSectionRow>
      </PanelSection>}
    </>}
    {page === "diagnostics" && <PanelSection title={t("health")}>
      {lifecycleView}
      {status?.checks.map(check => <PanelSectionRow key={check.id}><Field label={t(checkNames[check.id] ?? "health")}
        description={language === "ru" ? check.message : t(check.state === "ok" ? "verified" : check.state === "error" ? "needsCheck" : "unknown")}><span style={{ color: check.state === "ok" ? "#a7f3d0" : check.state === "error" ? "#fca5a5" : "#fcd34d" }}>
          {check.state === "ok" ? "✓" : check.state === "error" ? "!" : "?"}</span></Field></PanelSectionRow>)}
      <PanelSectionRow><Field description={t("temporaryProbe")} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !lifecycle?.native_runtime} onClick={() => void run(async () => {
        const result = await unwrap(rpc.probeRuntime("host-load")); await refresh();
        if (result.error) setError(result.error);
      })}>{t("hostLoad")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(() => refresh(true))}>{t("loaderProbe")}</ButtonItem></PanelSectionRow>
      {(probe?.interpretation || probe?.error) && <PanelSectionRow><Field description={probe.error ?? probe.interpretation} /></PanelSectionRow>}
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
        setNotice(`${t("exported")}: ${await unwrap(rpc.export())}`);
      })}>{t("export")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => void run(async () => {
        setProcesses(await unwrap(rpc.processes()));
      })}>{t("processes")}</ButtonItem></PanelSectionRow>
      {processes?.length === 0 && row(t("processes"), t("noProcesses"))}
      {processes?.map(p => row(`PID ${p.pid}`, `${p.executables.join(", ")} · ${t(p.layer_mapped ? "mapped" : "unmapped")}`))}
      <PanelSectionRow><ButtonItem disabled={busy || lifecycle?.read_only} onClick={() => void run(async () => {
        const count = await unwrap(rpc.importProfiles()); await refresh(); setNotice(`${t("imported")}: ${count}`);
      })}>{t("importProfiles")}</ButtonItem></PanelSectionRow>
    </PanelSection>}
    {page === "runtime" && <PanelSection title={t("runtime")}>
      {lifecycleView}
      {row(t("activeRuntime"), status?.runtime?.slot ?? t("absent"))}
      <PanelSectionRow><Field description={t("localOnly")} /></PanelSectionRow>
      <PanelSectionRow><TextField label={t("bundle")} value={directory} disabled={busy}
        onChange={event => setDirectory(event.target.value)} /></PanelSectionRow>
      <PanelSectionRow><TextField label={t("slot")} value={slot} disabled={busy}
        onChange={event => setSlot(event.target.value)} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !directory || !slot} onClick={() => void run(async () => {
        await unwrap(rpc.importRuntime(directory, slot)); await refresh(); setNotice(t("success"));
      })}>{t("importRuntime")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem label={t("runtime")} layout="below" disabled={busy || !runtimeOptions.length}
        onClick={() => setPicker("runtimeSlot")}>
        {runtimeOptions.find(option => option.data === selectedSlot)?.label ?? t("chooseRuntime")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><Field description={t("rollbackHint")} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !selectedSlot || !lifecycle?.activation_allowed} onClick={() => void run(async () => {
        await unwrap(rpc.activate(selectedSlot)); await refresh(); setNotice(t("success"));
      })}>{t("activate")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy} onClick={() => {
        if (!confirm) { setConfirm(true); return; }
        setConfirm(false); void run(async () => { await unwrap(rpc.rollback()); await refresh(); setNotice(t("success")); });
      }}>{t(confirm ? "confirmRollback" : "rollback")}</ButtonItem></PanelSectionRow>
    </PanelSection>}
    </>}
  </div>;
}

export default definePlugin(() => ({
  name: "ThorFG", titleView: <div className={staticClasses.Title}>ThorFG</div>,
  content: <Content />, icon: <FaBolt />, onDismount() {},
}));
