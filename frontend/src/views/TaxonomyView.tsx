import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, GitBranchPlus, Info, Upload, Download, Sparkles, Lock } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { ActivityFeed } from "@/components/ActivityFeed";
import { RunControls, RunProgress } from "@/components/RunControls";
import { TaxonomyTree } from "@/components/taxonomy/TaxonomyTree";
import { NodeDetail, NodeDetailEmpty } from "@/components/taxonomy/NodeDetail";
import { Proposals } from "@/components/taxonomy/Proposals";
import { Card, Spinner, Switch, Tabs, TabsContent, TabsList, TabsTrigger, Tip } from "@/components/ui/primitives";

export function TaxonomyView({ summary, selected, onSelect, openInteraction, openConversation }: {
  summary: Summary | undefined;
  selected: string | null;
  onSelect: (id: string | null) => void;
  openInteraction: (id: number) => void;
  openConversation: (cid: string) => void;
}) {
  const [showInactive, setShowInactive] = useState(false);
  const [panel, setPanel] = useState<string>("activity");
  const { data } = useQuery({ queryKey: ["taxonomy", showInactive], queryFn: () => api.taxonomy(showInactive) });
  const qc = useQueryClient();
  const upload = useMutation({
    mutationFn: api.importTaxonomy,
    onSuccess: () => qc.invalidateQueries(),
    onError: (e: Error) => alert(e.message),
  });
  const nodes = data?.nodes ?? [];
  const ai = nodes.filter((n) => n.level >= 3 && n.status === "active").length;
  const proposed = nodes.filter((n) => n.status === "proposed").length;
  const select = (id: string) => { onSelect(id); setPanel("details"); };
  const tab = selected && panel === "details" ? "details" : panel;

  return (
    <div className="flex h-[calc(100vh-88px)] min-h-[560px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">Taxonomy Explorer</h1>
          <p className="mt-0.5 flex items-center gap-3 text-xs text-zinc-500">
            <span className="flex items-center gap-1"><Lock className="size-3" />{nodes.filter((n) => n.level <= 2).length} fixed L1/L2</span>
            <span className="flex items-center gap-1 text-blue-600"><Sparkles className="size-3" />{ai} AI-generated L3/L4</span>
            {proposed > 0 && <span className="text-blue-500">{proposed} proposed</span>}
            {data && <span className="font-mono">v{data.version}</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            <Switch checked={showInactive} onCheckedChange={setShowInactive} /> Show merged & retired
          </label>
          <Tip content="Download the current L1/L2 taxonomy file">
            <a href="/api/taxonomy/base.json" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100"><Download className="size-4" /></a>
          </Tip>
          <Tip content="Load an L1/L2 taxonomy JSON (before analysis)">
            <label className="cursor-pointer rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100">
              <Upload className="size-4" />
              <input type="file" accept=".json" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
            </label>
          </Tip>
          <RunControls summary={summary} size="sm" />
        </div>
      </div>
      {summary && summary.interactions > 0 && <RunProgress summary={summary} />}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(380px,1fr)]">
        <Card className="flex min-h-0 flex-col pt-4">
          {!data ? <div className="flex flex-1 items-center justify-center text-zinc-400"><Spinner /></div> : (
            <TaxonomyTree nodes={nodes} selectedId={selected} onSelect={select} />
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-zinc-100 px-4 py-2 text-[11px] text-zinc-400">
            <span className="flex items-center gap-1"><span className="rounded bg-zinc-100 px-1 font-mono text-[10px] text-zinc-500">L2</span>fixed</span>
            <span className="flex items-center gap-1"><span className="rounded bg-blue-50 px-1 font-mono text-[10px] text-blue-600">L4</span>AI-generated</span>
            <span className="flex items-center gap-1"><span className="rounded border border-dashed border-blue-300 px-1 font-mono text-[10px] text-blue-600">L4</span>proposed</span>
            <span className="ml-auto">Numbers = associated interactions</span>
          </div>
        </Card>

        <Card className="flex min-h-0 flex-col">
          <Tabs value={tab} onValueChange={setPanel} className="flex min-h-0 flex-1 flex-col">
            <div className="px-4 pt-3 pb-3">
              <TabsList>
                <TabsTrigger value="activity"><Activity />Live activity</TabsTrigger>
                <TabsTrigger value="details" disabled={!selected}><Info />Details</TabsTrigger>
                <TabsTrigger value="proposals"><GitBranchPlus />Proposals{summary?.pending_proposals ? <span className="rounded-full bg-amber-100 px-1.5 text-[10px] text-amber-700">{summary.pending_proposals}</span> : null}</TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="activity" className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden" forceMount>
              <ActivityFeed className="min-h-0 flex-1" onOpenNode={select} onOpenConversation={openConversation} />
            </TabsContent>
            <TabsContent value="details" className="flex min-h-0 flex-1 flex-col">
              {selected ? <NodeDetail nodeId={selected} nodes={nodes} onSelect={select} onOpenInteraction={openInteraction} /> : <NodeDetailEmpty />}
            </TabsContent>
            <TabsContent value="proposals" className="flex min-h-0 flex-1 flex-col">
              <Proposals onSelectNode={select} />
            </TabsContent>
          </Tabs>
        </Card>
      </div>
    </div>
  );
}
