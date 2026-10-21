import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, CheckCircle2, Database, Download, FileUp, GitBranchPlus, ListChecks, Network, Sparkles, TriangleAlert } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useLive } from "@/lib/live";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { ActivityFeed } from "@/components/ActivityFeed";
import { DiscoveryCurve } from "@/components/DiscoveryCurve";
import { RunControls, RunProgress } from "@/components/RunControls";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Spinner } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import type { NavOptions } from "@/App";

export function Workspace({ summary, onImport, onImportTaxonomy, onExport, go, openConversation, openNode }: {
  summary: Summary | undefined;
  onImport: () => void;
  onImportTaxonomy: () => void;
  onExport: () => void;
  go: (view: string, opts?: NavOptions) => void;
  openConversation: (cid: string) => void;
  openNode: (id: string) => void;
}) {
  const { t, lang } = useI18n();
  const curve = useQuery({ queryKey: ["curve"], queryFn: api.curve, enabled: !!summary?.processed });

  if (!summary) return <div className="flex h-64 items-center justify-center text-zinc-400"><Spinner /></div>;

  if (!summary.interactions) {
    return (
      <div className="mx-auto max-w-2xl pt-16">
        <div className="text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600"><Sparkles className="size-6" /></div>
          {summary.project && <p className="mt-5 text-xs font-medium text-zinc-400">{t("workspace.project")}: {summary.project.name}</p>}
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900">{t("workspace.emptyTitle")}</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-zinc-500">{t("workspace.emptyText")}</p>
          <div className="mt-7 flex flex-wrap justify-center gap-2">
            <Button size="lg" onClick={onImport}><FileUp />{t("workspace.importData")}</Button>
            <Button size="lg" variant="secondary" onClick={onImportTaxonomy}><Network />{t("workspace.importTaxonomy")}</Button>
          </div>
          <p className="mx-auto mt-3 max-w-lg text-xs text-zinc-400">
            {summary.l2_nodes ? t("workspace.taxonomyHint", { l1: summary.l1_nodes, l2: summary.l2_nodes, lang: t(`languages.${summary.taxonomy_language}`) }) : t("workspace.taxonomyMissing")}
          </p>
        </div>
        <ol className="mt-14 grid grid-cols-3 gap-3">
          {(["import", "analyse", "review"] as const).map((k, i) => (
            <li key={k} className="rounded-xl border border-zinc-200/80 bg-white p-4">
              <span className="font-mono text-xs text-blue-600">0{i + 1}</span>
              <p className="mt-1 text-sm font-medium text-zinc-900">{t(`workspace.steps.${k}.title`)}</p>
              <p className="mt-1 text-xs leading-relaxed text-zinc-500">{t(`workspace.steps.${k}.text`)}</p>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  const stats = [
    { key: "imported", value: summary.interactions, icon: Database, onClick: () => go("interactions") },
    { key: "processed", value: summary.processed, icon: CheckCircle2, sub: summary.failed ? t("workspace.sub.failed", { count: summary.failed }) : undefined, onClick: () => go("interactions") },
    { key: "discovered", value: summary.discovered_intents, icon: Sparkles, sub: t("workspace.sub.extracted", { count: summary.intents_extracted }), onClick: () => go("taxonomy") },
    { key: "nodes", value: `${summary.l3_nodes} / ${summary.l4_nodes}`, icon: Boxes, sub: t("workspace.sub.version", { v: summary.taxonomy_version }), onClick: () => go("taxonomy") },
    { key: "needsReview", value: summary.needs_review, icon: TriangleAlert, sub: summary.unclassified ? t("workspace.sub.unclassified", { count: summary.unclassified }) : undefined, warn: summary.needs_review > 0, onClick: () => go("interactions", { review: "needs_review" }) },
    { key: "proposals", value: summary.pending_proposals, icon: GitBranchPlus, sub: summary.overlapping_categories ? t("workspace.sub.overlaps", { count: summary.overlapping_categories }) : undefined, warn: summary.pending_proposals > 0, onClick: () => go("taxonomy", { panel: "proposals" }) },
  ];
  const latest = summary.imports[0];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-zinc-400">{t("workspace.project")}</p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">{summary.project?.name ?? summary.dataset}</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            {t("workspace.dataset")}: {summary.dataset} · {t("workspace.imports", { count: summary.imports.length })}
            {latest && ` · ${t("workspace.lastImport")} ${formatDateTime(latest.created_at, lang)}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={onImport}><FileUp />{t("workspace.importData")}</Button>
          <Button variant="secondary" onClick={onExport} disabled={!summary.processed}><Download />{t("header.export")}</Button>
          <RunControls summary={summary} />
        </div>
      </div>

      {!summary.l2_nodes && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50/60 px-5 py-3.5">
          <TriangleAlert className="size-4 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-900">{t("workspace.taxonomyMissingTitle")}</p>
            <p className="text-xs text-amber-800">{t("workspace.taxonomyMissingText")}</p>
          </div>
          <Button size="sm" onClick={onImportTaxonomy}><Network />{t("workspace.importTaxonomy")}</Button>
        </div>
      )}

      <Card className="px-5 py-4"><RunProgress summary={summary} /></Card>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => (
          <button key={s.key} onClick={s.onClick} className="group rounded-xl border border-zinc-200/80 bg-white px-4 py-3.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition hover:border-zinc-300 cursor-pointer">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium text-zinc-500">{t(`workspace.stats.${s.key}`)}</span>
              <s.icon className={cn("size-3.5", s.warn && "text-amber-500")} />
            </div>
            <p key={String(s.value)} className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900 tabular-nums animate-fade-in">{s.value}</p>
            <p className="h-4 text-[11px] text-zinc-400">{s.sub}</p>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:h-[560px] lg:grid-cols-[1.35fr_1fr]">
        <Card className="flex h-[520px] flex-col lg:h-auto lg:min-h-0">
          <CardHeader title={t("workspace.activityTitle")} />
          <ActivityFeed className="min-h-0 flex-1" onOpenConversation={openConversation} onOpenNode={openNode} />
        </Card>
        <div className="flex min-h-0 flex-col gap-5">
          <Card>
            <CardHeader title={t("workspace.curveTitle")} description={t("workspace.curveText")} />
            <div className="px-4 pb-4"><DiscoveryCurve curve={curve.data} /></div>
          </Card>
          <RecentCategories openNode={openNode} go={go} />
        </div>
      </div>
    </div>
  );
}

function RecentCategories({ openNode, go }: { openNode: (id: string) => void; go: (v: string) => void }) {
  const { t, lang } = useI18n();
  const { events } = useLive();
  const recent = useMemo(() => events.filter((e) => ["category_approved", "category_proposed", "category_refined", "merge_proposed", "split_proposed"].includes(e.kind)).slice(0, 7), [events]);
  return (
    <Card className="flex min-h-0 flex-1 flex-col">
      <CardHeader title={t("workspace.recentTitle")} action={<Button size="xs" variant="ghost" onClick={() => go("taxonomy")}>{t("workspace.explorer")}<ArrowRight /></Button>} />
      <ul className="scroll-thin min-h-0 flex-1 overflow-auto px-2 pb-3">
        {recent.length === 0 && <li className="px-3 pb-3 text-xs text-zinc-400">{t("workspace.recentEmpty")}</li>}
        {recent.map((e) => (
          <li key={e.id}>
            <button className="flex w-full items-start gap-2 rounded-lg px-3 py-1.5 text-left hover:bg-zinc-50 cursor-pointer animate-fade-in" onClick={() => e.node_id && openNode(e.node_id)}>
              <ListChecks className={cn("mt-0.5 size-3.5 shrink-0", e.kind === "category_approved" ? "text-emerald-500" : e.kind.includes("merge") || e.kind.includes("split") ? "text-amber-500" : "text-blue-500")} />
              <span className="flex-1 text-[13px] text-zinc-700">{e.message}</span>
              <span className="shrink-0 text-[11px] text-zinc-400">{timeAgo(e.created_at, lang)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
