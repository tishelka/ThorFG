import { ButtonItem, Field, PanelSection, PanelSectionRow, TextField } from "@decky/ui";
import { useState } from "react";
import { Key } from "./i18n";

type Option = { value: string; label: string };
type Props = {
  title: string; options: Option[]; selected: string; disabled: boolean;
  t: (key: Key) => string; onSelect: (value: string) => void; onClose: () => void;
};

const PAGE_SIZE = 20;

// Uses the panel's normal scrolling/focus navigation, with a bounded number of
// ButtonItems. Both controller activation and touch use the same onClick handler.
export function SelectionList({ title, options, selected, disabled, t, onSelect, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const search = query.trim().toLocaleLowerCase();
  const filtered = options.filter(option => option.label.toLocaleLowerCase().includes(search));
  const lastPage = Math.max(0, Math.ceil(filtered.length / PAGE_SIZE) - 1);
  const currentPage = Math.min(page, lastPage);
  const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  return <PanelSection title={title}>
    <PanelSectionRow><ButtonItem disabled={disabled} onClick={onClose}>
      {t("backToSection")}</ButtonItem></PanelSectionRow>
    <PanelSectionRow><TextField label={t("searchChoices")} value={query} disabled={disabled}
      onChange={event => { setQuery(event.target.value); setPage(0); }} /></PanelSectionRow>
    {!!query && <PanelSectionRow><ButtonItem disabled={disabled} onClick={() => { setQuery(""); setPage(0); }}>
      {t("clearSearch")}</ButtonItem></PanelSectionRow>}
    <PanelSectionRow><Field label={t("choiceCount")} description={`${filtered.length} / ${options.length}`} /></PanelSectionRow>
    {!visible.length && <PanelSectionRow><Field description={t("noMatches")} /></PanelSectionRow>}
    {visible.map(option => <PanelSectionRow key={option.value}>
      <ButtonItem layout="below" disabled={disabled}
        description={selected === option.value ? t("currentSelection") : undefined}
        onClick={() => onSelect(option.value)}>
        <span style={{ whiteSpace: "normal", overflowWrap: "anywhere" }}>
          {selected === option.value ? "✓ " : ""}{option.label}
        </span>
      </ButtonItem>
    </PanelSectionRow>)}
    {lastPage > 0 && <>
      <PanelSectionRow><Field label={t("listPage")} description={`${currentPage + 1} / ${lastPage + 1}`} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={disabled || currentPage === 0} onClick={() => setPage(currentPage - 1)}>
        {t("previousChoices")}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={disabled || currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>
        {t("nextChoices")}</ButtonItem></PanelSectionRow>
    </>}
  </PanelSection>;
}
