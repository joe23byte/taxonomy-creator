import { useCallback, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Download, FolderKanban, LayoutDashboard, Network, Settings as SettingsIcon, Table2 } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Tip } from "@/components/ui/primitives";
import { SettingsDialog } from "@/components/SettingsDialog";
import { ImportDialog } from "@/components/ImportDialog";
import { ExportDialog } from "@/components/ExportDialog";
import { InteractionDetail } from "@/components/interaction/InteractionDetail";
import { LanguageSwitch, ProjectSwitcher } from "@/components/ProjectSwitcher";
import { runPhase } from "@/components/RunControls";
import { Workspace } from "@/views/Workspace";
import { TaxonomyView } from "@/views/TaxonomyView";
import { InteractionsView } from "@/views/InteractionsView";
import { InsightsView } from "@/views/InsightsView";
import { ProjectsView } from "@/views/ProjectsView";

const VIEWS = [
  { id: "workspace", icon: LayoutDashboard },
  { id: "taxonomy", icon: Network },
  { id: "interactions", icon: Table2 },
  { id: "insights", icon: BarChart3 },
] as const;
const ALL_VIEWS = [...VIEWS.map((v) => v.id), "projects"] as const;
type View = (typeof ALL_VIEWS)[number];
export type NavOptions = { review?: string; classification?: string; panel?: string };

function useHashView(): [View, (v: string) => void] {
  const read = () => (ALL_VIEWS.find((v) => `#/${v}` === window.location.hash) ?? "workspace") as View;
  const [view, setView] = useState<View>(read);
  useEffect(() => {
    const onHash = () => setView(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [view, (v: string) => { window.location.hash = `/${v}`; }];
}

export default function App() {
  const [view, go] = useHashView();
  const qc = useQueryClient();
  const { t } = useI18n();
  const { focusedInteraction, focusInteraction } = useLive();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [importTab, setImportTab] = useState<"interactions" | "taxonomy" | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [nav, setNav] = useState<NavOptions & { n: number }>({ n: 0 });
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: (q) => (q.state.data?.worker_alive ? 4000 : 15000) });
  const { running } = runPhase(summary.data);

  // Options apply once, to the view opened with them; plain navigation clears them.
  const navigate = useCallback((v: string, opts: NavOptions = {}) => {
    setNav((p) => ({ ...opts, n: p.n + 1 }));
    go(v);
  }, [go]);
  const openNode = useCallback((id: string) => {
    setSelectedNode(id);
    focusInteraction(null);
    navigate("taxonomy", { panel: "details" });
  }, [navigate, focusInteraction]);
  const openConversation = useCallback(async (cid: string) => {
    const rows = await qc.fetchQuery({ queryKey: ["interactions"], queryFn: api.interactions, staleTime: 3000 });
    const row = rows.find((r) => r.conversation_id === cid);
    if (row) focusInteraction(row.id);
  }, [qc, focusInteraction]);

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-zinc-200/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1480px] items-center gap-4 px-6">
          <div className="flex items-center gap-1">
            <a href="#/workspace" className="flex items-center gap-2 pr-1">
              <Logo />
              <span className="text-[15px] font-semibold tracking-tight text-zinc-900">Intent Studio</span>
            </a>
            <span className="text-zinc-300">/</span>
            <ProjectSwitcher name={summary.data?.project?.name} locked={running} />
          </div>
          <nav className="flex items-center gap-0.5">
            {VIEWS.map((v) => (
              <button key={v.id} onClick={() => navigate(v.id)}
                className={cn("flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium transition cursor-pointer",
                  view === v.id ? "bg-zinc-100 text-zinc-900" : "text-zinc-500 hover:text-zinc-900")}>
                <v.icon className="size-3.5" />{t(`nav.${v.id}`)}
                {v.id === "taxonomy" && running && <span className="size-1.5 animate-pulse rounded-full bg-blue-600" />}
                {v.id === "interactions" && !!summary.data?.needs_review && (
                  <span className="rounded-full bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-700">{summary.data.needs_review}</span>
                )}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ConnectionIndicator onClick={() => setSettingsOpen(true)} />
            <Button size="sm" variant="secondary" onClick={() => setExportOpen(true)} disabled={!summary.data?.processed}>
              <Download />{t("header.export")}
            </Button>
            <LanguageSwitch />
            <Tip content={t("nav.projects")} side="bottom">
              <Button size="icon" variant="ghost" onClick={() => navigate("projects")} aria-label={t("nav.projects")}
                className={cn(view === "projects" && "bg-zinc-100")}><FolderKanban /></Button>
            </Tip>
            <Tip content={t("settings.title")} side="bottom">
              <Button size="icon" variant="ghost" onClick={() => setSettingsOpen(true)} aria-label={t("settings.title")}><SettingsIcon /></Button>
            </Tip>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1480px] flex-1 px-6 py-5">
        {view === "workspace" && (
          <Workspace summary={summary.data} onImport={() => setImportTab("interactions")} onImportTaxonomy={() => setImportTab("taxonomy")}
            onExport={() => setExportOpen(true)} go={navigate} openConversation={openConversation} openNode={openNode} />
        )}
        {view === "taxonomy" && (
          <TaxonomyView key={nav.n} initialPanel={nav.panel} summary={summary.data} selected={selectedNode} onSelect={setSelectedNode}
            openInteraction={(id) => focusInteraction(id)} openConversation={openConversation} />
        )}
        {view === "interactions" && <InteractionsView key={nav.n} initialReview={nav.review} initialClassification={nav.classification} openInteraction={(id) => focusInteraction(id)} />}
        {view === "insights" && <InsightsView summary={summary.data} openNode={openNode} go={navigate} />}
        {view === "projects" && <ProjectsView />}
      </main>

      <Sheet open={focusedInteraction != null} onOpenChange={(o) => !o && focusInteraction(null)} title={t("interaction.title")}>
        {focusedInteraction != null && <InteractionDetail id={focusedInteraction} onOpenNode={openNode} />}
      </Sheet>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      <ImportDialog open={importTab != null} initialTab={importTab ?? "interactions"} onOpenChange={(o) => !o && setImportTab(null)} />
      <ExportDialog open={exportOpen} onOpenChange={setExportOpen} />
    </div>
  );
}

function ConnectionIndicator({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["ollama-status"], queryFn: api.ollamaStatus, refetchInterval: 30000 });
  const state = isLoading ? "checking" : data?.ok ? "ok" : data?.reachable ? "missing" : "offline";
  const dot = { checking: "bg-zinc-300", ok: "bg-emerald-500", missing: "bg-amber-500", offline: "bg-red-500" }[state];
  const tip = data
    ? data.ok ? data.url
      : data.missing?.length ? t("connection.missingOn", { url: data.url, models: data.missing.join(", ") })
        : `${data.url} — ${data.error ?? t("connection.unreachable")}`
    : "";
  return (
    <Tip content={tip} side="bottom">
      <button onClick={onClick} className="flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs text-zinc-500 hover:bg-zinc-100 cursor-pointer">
        <span className={cn("size-1.5 rounded-full", dot)} />{t(`connection.${state}`)}
      </button>
    </Tip>
  );
}

function Logo() {
  const { data } = useQuery({ queryKey: ["branding"], queryFn: api.branding, staleTime: Infinity });
  if (data?.logo) return <img src={`/api/branding/logo?v=${data.version}`} alt="" className="h-6 max-w-[140px] object-contain" />;
  return (
    <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
      <rect width="24" height="24" rx="6" fill="#2563eb" />
      <path d="M7 7.5h4M7 12h7M7 16.5h10" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="13.5" cy="7.5" r="1.4" fill="white" />
    </svg>
  );
}
