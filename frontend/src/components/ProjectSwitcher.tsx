import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronsUpDown, FolderKanban, FolderPlus } from "lucide-react";
import { api } from "@/lib/api";
import { LANGUAGES, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { CreateProjectDialog, openProject } from "@/views/ProjectsView";

const item = "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-zinc-700 outline-none data-[highlighted]:bg-zinc-100 data-[disabled]:cursor-default data-[disabled]:opacity-50";

export function ProjectSwitcher({ name, locked }: { name?: string; locked: boolean }) {
  const { t } = useI18n();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data, refetch } = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: false });
  return (
    <>
      <Menu.Root onOpenChange={(o) => { if (o) { setError(null); refetch(); } }}>
        <Menu.Trigger asChild>
          <button className="flex h-8 max-w-56 items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium text-zinc-700 hover:bg-zinc-100 cursor-pointer" aria-label={t("projects.switch")}>
            <FolderKanban className="size-3.5 shrink-0 text-zinc-400" />
            <span className="truncate">{name ?? "…"}</span>
            <ChevronsUpDown className="size-3 shrink-0 text-zinc-400" />
          </button>
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content align="start" sideOffset={6} className="z-50 w-72 rounded-xl border border-zinc-200 bg-white p-1.5 shadow-lg animate-fade-in">
            <Menu.Label className="px-2 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{t("projects.title")}</Menu.Label>
            {!data ? <p className="px-2 py-1.5 text-xs text-zinc-400">…</p> : data.projects.map((p) => (
              <Menu.Item key={p.id} className={item} disabled={p.id !== data.active && locked}
                onSelect={() => p.id !== data.active && openProject(p.id).catch((e: Error) => setError(e.message))}>
                <Check className={cn("size-3.5 shrink-0", p.id === data.active ? "text-blue-600" : "invisible")} />
                <span className="truncate">{p.name}</span>
                <span className="ml-auto shrink-0 text-[11px] tabular-nums text-zinc-400">{p.stats?.interactions ?? 0}</span>
              </Menu.Item>
            ))}
            {locked && <p className="px-2 py-1 text-[11px] text-amber-700">{t("projects.lockedHint")}</p>}
            {error && <p className="px-2 py-1 text-[11px] text-red-600">{error}</p>}
            <Menu.Separator className="my-1 h-px bg-zinc-100" />
            <Menu.Item className={item} disabled={locked} onSelect={() => setCreating(true)}><FolderPlus className="size-3.5" />{t("projects.new")}</Menu.Item>
            <Menu.Item className={item} onSelect={() => { window.location.hash = "/projects"; }}><FolderKanban className="size-3.5" />{t("projects.manage")}</Menu.Item>
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
      <CreateProjectDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="flex h-8 items-center rounded-lg bg-zinc-100 p-0.5" role="radiogroup" aria-label={t("common.language")}>
      {(Object.keys(LANGUAGES) as Lang[]).map((l) => (
        <button key={l} role="radio" aria-checked={lang === l} title={LANGUAGES[l]} onClick={() => setLang(l)}
          className={cn("h-7 rounded-md px-2 text-[11px] font-semibold uppercase cursor-pointer",
            lang === l ? "bg-white text-zinc-900 shadow-xs" : "text-zinc-500 hover:text-zinc-800")}>
          {l}
        </button>
      ))}
    </div>
  );
}
