import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Boxes, CheckCircle2, Database, Download, FileUp, GitBranchPlus, ListChecks, Sparkles, TriangleAlert } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { useLive } from "@/lib/live";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { ActivityFeed } from "@/components/ActivityFeed";
import { DiscoveryCurve } from "@/components/DiscoveryCurve";
import { RunControls, RunProgress } from "@/components/RunControls";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Spinner } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export function Workspace({ summary, onImport, onExport, go, openConversation, openNode }: {
  summary: Summary | undefined;
  onImport: () => void;
  onExport: () => void;
  go: (view: string) => void;
  openConversation: (cid: string) => void;
  openNode: (id: string) => void;
}) {
  const qc = useQueryClient();
  const sample = useMutation({ mutationFn: api.loadSample, onSuccess: () => qc.invalidateQueries() });
  const curve = useQuery({ queryKey: ["curve"], queryFn: api.curve, enabled: !!summary?.processed });

  if (!summary) return <div className="flex h-64 items-center justify-center text-zinc-400"><Spinner /></div>;

  if (!summary.interactions) {
    return (
      <div className="mx-auto max-w-2xl pt-16">
        <div className="text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600"><Sparkles className="size-6" /></div>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-900">Discover what your customers really ask for</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-zinc-500">
            Intent Studio reads conversation transcripts, extracts atomic customer intents with a local LLM and grows a
            traceable L1–L4 taxonomy from them — with you in control of every change.
          </p>
          <div className="mt-7 flex justify-center gap-2">
            <Button size="lg" onClick={() => sample.mutate()} disabled={sample.isPending}>
              {sample.isPending ? <Spinner /> : <Sparkles />}Load 100 Sample Interactions
            </Button>
            <Button size="lg" variant="secondary" onClick={onImport}><FileUp />Import Data</Button>
          </div>
        </div>
        <ol className="mt-14 grid grid-cols-3 gap-3">
          {[
            ["Import", "Transcripts from JSON, CSV, Excel or TXT, plus the predefined L1/L2 taxonomy."],
            ["Analyse", "Intents are extracted, embedded and clustered; L3/L4 categories emerge batch by batch."],
            ["Review & export", "Confirm or correct assignments, approve structural changes, export to Excel."],
          ].map(([t, d], i) => (
            <li key={t} className="rounded-xl border border-zinc-200/80 bg-white p-4">
              <span className="font-mono text-xs text-blue-600">0{i + 1}</span>
              <p className="mt-1 text-sm font-medium text-zinc-900">{t}</p>
              <p className="mt-1 text-xs leading-relaxed text-zinc-500">{d}</p>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  const stats = [
    { label: "Imported", value: summary.interactions, icon: Database, onClick: () => go("interactions") },
    { label: "Processed", value: summary.processed, icon: CheckCircle2, sub: summary.failed ? `${summary.failed} failed` : undefined, onClick: () => go("interactions") },
    { label: "Discovered intents", value: summary.discovered_intents, icon: Sparkles, sub: `${summary.intents_extracted} extracted`, onClick: () => go("taxonomy") },
    { label: "L3 / L4 nodes", value: `${summary.l3_nodes} / ${summary.l4_nodes}`, icon: Boxes, sub: `taxonomy v${summary.taxonomy_version}`, onClick: () => go("taxonomy") },
    { label: "Needs review", value: summary.needs_review, icon: TriangleAlert, sub: summary.unclassified ? `${summary.unclassified} unclassified` : undefined, warn: summary.needs_review > 0, onClick: () => go("interactions") },
    { label: "Proposals", value: summary.pending_proposals, icon: GitBranchPlus, sub: summary.overlapping_categories ? `${summary.overlapping_categories} overlaps` : undefined, warn: summary.pending_proposals > 0, onClick: () => go("taxonomy") },
  ];
  const latest = summary.imports[0];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-zinc-400">Current dataset</p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">{summary.dataset}</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            {summary.imports.length} import{summary.imports.length > 1 ? "s" : ""} · last {latest && formatDateTime(latest.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={onImport}><FileUp />Import Data</Button>
          <Button variant="secondary" onClick={onExport} disabled={!summary.processed}><Download />Export Results</Button>
          <RunControls summary={summary} />
        </div>
      </div>

      <Card className="px-5 py-4"><RunProgress summary={summary} /></Card>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => (
          <button key={s.label} onClick={s.onClick} className="group rounded-xl border border-zinc-200/80 bg-white px-4 py-3.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition hover:border-zinc-300 cursor-pointer">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium text-zinc-500">{s.label}</span>
              <s.icon className={cn("size-3.5", s.warn && "text-amber-500")} />
            </div>
            <p key={String(s.value)} className="mt-1.5 text-2xl font-semibold tracking-tight text-zinc-900 tabular-nums animate-fade-in">{s.value}</p>
            <p className="h-4 text-[11px] text-zinc-400">{s.sub}</p>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Card className="flex h-[520px] flex-col">
          <CardHeader title="Live processing activity" description="Every entry reflects a completed backend operation." />
          <ActivityFeed className="min-h-0 flex-1" onOpenConversation={openConversation} onOpenNode={openNode} />
        </Card>
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title="Intent discovery curve" description="Distinct L4 categories observed vs. interactions analysed. Dashed lines mark batch refinements." />
            <div className="px-4 pb-4"><DiscoveryCurve curve={curve.data} /></div>
          </Card>
          <RecentCategories openNode={openNode} go={go} />
        </div>
      </div>
    </div>
  );
}

function RecentCategories({ openNode, go }: { openNode: (id: string) => void; go: (v: string) => void }) {
  const { events } = useLive();
  const recent = useMemo(() => events.filter((e) => ["category_approved", "category_proposed", "category_refined", "merge_proposed", "split_proposed"].includes(e.kind)).slice(0, 7), [events]);
  return (
    <Card className="flex-1">
      <CardHeader title="New & modified categories" action={<Button size="xs" variant="ghost" onClick={() => go("taxonomy")}>Explorer<ArrowRight /></Button>} />
      <ul className="px-2 pb-3">
        {recent.length === 0 && <li className="px-3 pb-3 text-xs text-zinc-400">Categories appear after the first batch refinement.</li>}
        {recent.map((e) => (
          <li key={e.id}>
            <button className="flex w-full items-start gap-2 rounded-lg px-3 py-1.5 text-left hover:bg-zinc-50 cursor-pointer animate-fade-in" onClick={() => e.node_id && openNode(e.node_id)}>
              <ListChecks className={cn("mt-0.5 size-3.5 shrink-0", e.kind === "category_approved" ? "text-emerald-500" : e.kind.includes("merge") || e.kind.includes("split") ? "text-amber-500" : "text-blue-500")} />
              <span className="flex-1 text-[13px] text-zinc-700">{e.message}</span>
              <span className="shrink-0 text-[11px] text-zinc-400">{timeAgo(e.created_at)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
