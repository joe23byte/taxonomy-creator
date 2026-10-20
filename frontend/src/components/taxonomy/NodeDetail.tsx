import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowRightLeft, ChevronRight, GitMerge, History, Lock, MessageSquareQuote, Pencil, Plus, Sparkles } from "lucide-react";
import { api, type Change, type TaxNode } from "@/lib/api";
import { cn, formatDateTime, sim, timeAgo } from "@/lib/utils";
import { Button } from "../ui/button";
import { Badge, Empty, Input, Select, Spinner, Textarea } from "../ui/primitives";

export function NodeDetail({ nodeId, nodes, onSelect, onOpenInteraction }: {
  nodeId: string; nodes: TaxNode[]; onSelect: (id: string) => void; onOpenInteraction: (id: number) => void;
}) {
  const qc = useQueryClient();
  const { data: node, isLoading } = useQuery({ queryKey: ["node", nodeId], queryFn: () => api.node(nodeId) });
  const [mode, setMode] = useState<"view" | "edit" | "merge" | "move" | "add">("view");
  const [label, setLabel] = useState("");
  const [desc, setDesc] = useState("");
  const [target, setTarget] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["taxonomy"] });
    qc.invalidateQueries({ queryKey: ["node"] });
    qc.invalidateQueries({ queryKey: ["proposals"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
    setMode("view");
    setError(null);
  };
  const mutate = useMutation({
    mutationFn: async (fn: () => Promise<unknown>) => fn(),
    onSuccess: refresh,
    onError: (e: Error) => setError(e.message),
  });

  if (isLoading || !node) return <div className="flex h-40 items-center justify-center text-zinc-400"><Spinner /></div>;

  const fixed = node.level <= 2;
  const l2Ancestor = node.path.find((p) => p.level === 2)?.id;
  const sameLevelInL2 = nodes.filter((n) => n.level === node.level && n.id !== node.id && n.status === "active" && ancestorL2(n, nodes) === l2Ancestor);
  const moveTargets = nodes.filter((n) => n.level === node.level - 1 && n.status === "active" && (node.level === 4 ? n.level === 3 : n.level === 2));

  return (
    <div className="flex min-h-0 flex-col">
      <div className="border-b border-zinc-100 px-5 pb-4">
        <nav className="mb-2 flex flex-wrap items-center gap-1 text-xs text-zinc-400">
          {node.path.slice(0, -1).map((p) => (
            <span key={p.id} className="flex items-center gap-1">
              <button className="hover:text-zinc-700 cursor-pointer" onClick={() => onSelect(p.id)}>{p.label}</button>
              <ChevronRight className="size-3" />
            </span>
          ))}
        </nav>
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-zinc-900">{node.label}</h2>
          {fixed ? <Badge><Lock />Fixed L{node.level}</Badge> : <Badge tone={node.status === "proposed" ? "dashed" : "blue"}><Sparkles />{node.source === "manual" ? "Manual" : "AI-generated"} L{node.level}</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span className="font-mono">{node.id}</span>·
          <span>{node.interaction_count} interactions</span>·
          <span>{node.intent_count} intents</span>
          {node.status !== "active" && <Badge tone="amber">{node.status}{node.merged_into ? ` → ${node.merged_into}` : ""}</Badge>}
        </div>
        {mode === "view" && (
          <p className="mt-3 text-sm leading-relaxed text-zinc-600">{node.description || <span className="italic text-zinc-400">No description</span>}</p>
        )}
        {mode === "edit" && (
          <div className="mt-3 space-y-2">
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" />
            <Textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description" />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => mutate.mutate(() => api.updateNode(node.id, { label, description: desc }))}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Cancel</Button>
            </div>
          </div>
        )}
        {mode === "add" && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-zinc-500">New L{node.level + 1} category under “{node.label}”</p>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" />
            <Textarea rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description" />
            <div className="flex gap-2">
              <Button size="sm" disabled={!label.trim()} onClick={() => mutate.mutate(() => api.createNode({ parent_id: node.id, label, description: desc }))}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Cancel</Button>
            </div>
          </div>
        )}
        {(mode === "merge" || mode === "move") && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-zinc-500">
              {mode === "merge"
                ? "Merge this category into another one. Unreviewed assignments move to the target; reviewed ones are kept and flagged."
                : "Move this category under another parent. Assignment paths are updated."}
            </p>
            <Select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Select {mode === "merge" ? "target category" : "new parent"}…</option>
              {(mode === "merge" ? sameLevelInL2 : moveTargets).map((n) => <option key={n.id} value={n.id}>{n.label} ({n.id})</option>)}
            </Select>
            <div className="flex gap-2">
              <Button size="sm" disabled={!target}
                onClick={() => mutate.mutate(() => mode === "merge" ? api.mergeNodes(node.id, target) : api.moveNode(node.id, target))}>
                {mode === "merge" ? "Merge" : "Move"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Cancel</Button>
            </div>
          </div>
        )}
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        {mode === "view" && node.status === "active" && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Button size="xs" variant="secondary" onClick={() => { setLabel(node.label); setDesc(node.description); setMode("edit"); }}><Pencil />Edit</Button>
            {node.level < 4 && <Button size="xs" variant="secondary" onClick={() => { setLabel(""); setDesc(""); setMode("add"); }}><Plus />Add L{node.level + 1}</Button>}
            {!fixed && <Button size="xs" variant="secondary" onClick={() => { setTarget(""); setMode("merge"); }}><GitMerge />Merge into…</Button>}
            {!fixed && <Button size="xs" variant="secondary" onClick={() => { setTarget(""); setMode("move"); }}><ArrowRightLeft />Move</Button>}
            {!fixed && (
              <Button size="xs" variant="ghost" className="text-zinc-500"
                onClick={() => confirm(`Retire “${node.label}”? It stays in the history; unreviewed assignments return to the candidate pool.`) && mutate.mutate(() => api.retireNode(node.id))}>
                <Archive />Retire
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="scroll-thin min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4">
        {node.children.length > 0 && (
          <section>
            <SectionTitle>Sub-categories</SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {node.children.map((c) => (
                <button key={c.id} onClick={() => onSelect(c.id)}
                  className={cn("rounded-md border px-2 py-1 text-xs hover:bg-zinc-50 cursor-pointer", c.status === "proposed" ? "border-dashed border-blue-300 text-blue-700" : "border-zinc-200 text-zinc-700")}>
                  {c.label}
                </button>
              ))}
            </div>
          </section>
        )}

        <section>
          <SectionTitle icon={<MessageSquareQuote className="size-3.5" />}>
            Supporting customer statements {node.examples.length > 0 && <span className="text-zinc-400">({node.examples.length})</span>}
          </SectionTitle>
          {node.status === "proposed" && node.proposal_members.length > 0 && (
            <ul className="space-y-1.5">
              {node.proposal_members.map((m) => (
                <Statement key={m.id} text={m.intent_text} evidence={m.evidence} cid={m.conversation_id} onOpen={() => onOpenInteraction(m.interaction_id)} />
              ))}
            </ul>
          )}
          {node.examples.length === 0 && node.status !== "proposed" ? (
            <p className="text-xs text-zinc-400">No interactions assigned yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {node.examples.slice(0, 25).map((e) => (
                <Statement key={e.assignment_id} text={e.intent_text} evidence={e.evidence} cid={e.conversation_id}
                  similarity={e.similarity} status={e.review_status} onOpen={() => onOpenInteraction(e.interaction_id)} />
              ))}
            </ul>
          )}
        </section>

        <section>
          <SectionTitle icon={<History className="size-3.5" />}>Creation & revision history</SectionTitle>
          {node.history.length === 0 ? (
            <p className="text-xs text-zinc-400">{fixed ? "Predefined category — unchanged." : "No recorded changes."}</p>
          ) : (
            <ol className="relative space-y-3 border-l border-zinc-200 pl-4">
              {node.history.map((h) => <HistoryItem key={h.id} h={h} />)}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}

function ancestorL2(n: TaxNode, nodes: TaxNode[]): string | undefined {
  let cur: TaxNode | undefined = n;
  while (cur && cur.level > 2) cur = nodes.find((x) => x.id === cur!.parent_id);
  return cur?.level === 2 ? cur.id : undefined;
}

function SectionTitle({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-400">{icon}{children}</h4>;
}

function Statement({ text, evidence, cid, similarity, status, onOpen }: {
  text: string; evidence: string | null; cid: string; similarity?: number | null; status?: string; onOpen: () => void;
}) {
  return (
    <li className="group rounded-lg border border-zinc-100 bg-zinc-50/50 px-3 py-2 hover:border-zinc-200 hover:bg-white cursor-pointer" onClick={onOpen}>
      {evidence && <p className="text-[13px] leading-snug text-zinc-800">“{evidence}”</p>}
      <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-500">
        <span className="truncate">{text}</span>
        <span className="ml-auto shrink-0 font-mono text-zinc-400 group-hover:text-blue-600">{cid}</span>
        {similarity != null && <span className="shrink-0 font-mono text-zinc-400">sim {sim(similarity)}</span>}
        {status && status !== "pending" && <Badge tone={status === "confirmed" ? "green" : status === "corrected" ? "blue" : "neutral"}>{status}</Badge>}
      </div>
    </li>
  );
}

const CHANGE_LABEL: Record<string, string> = {
  create: "Created", update: "Edited", refine: "Description refined", merge: "Merge", split: "Split", retire: "Retired", move: "Moved",
};

function HistoryItem({ h }: { h: Change }) {
  const tone = h.status === "proposed" ? "amber" : h.status === "rejected" ? "neutral" : "green";
  return (
    <li className="relative">
      <span className={cn("absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-white",
        tone === "amber" ? "bg-amber-400" : tone === "green" ? "bg-emerald-500" : "bg-zinc-300")} />
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-medium text-zinc-800">{CHANGE_LABEL[h.change_type] ?? h.change_type}</span>
        <Badge tone={tone}>{h.status.replace("_", " ")}</Badge>
        <Badge tone="outline">{h.source === "ai" ? "AI" : "User"}</Badge>
        {h.version && <span className="font-mono text-[10px] text-zinc-400">v{h.version}</span>}
        <span className="ml-auto text-[11px] text-zinc-400" title={formatDateTime(h.created_at)}>{timeAgo(h.created_at)}</span>
      </div>
      {h.rationale && <p className="mt-0.5 text-xs text-zinc-500">{h.rationale}</p>}
      {h.change_type === "refine" && h.previous?.description && (
        <p className="mt-1 text-xs text-zinc-400 line-through">{h.previous.description}</p>
      )}
      {h.change_type === "update" && h.previous && (
        <p className="mt-1 text-xs text-zinc-400">Was: {h.previous.label}</p>
      )}
      {h.change_type === "merge" && h.proposed && (
        <p className="mt-1 text-xs text-zinc-500">“{h.proposed.source_label}” → “{h.proposed.target_label}”{h.proposed.similarity ? ` · similarity ${h.proposed.similarity.toFixed(2)}` : ""}</p>
      )}
      {h.change_type === "create" && h.proposed?.cluster && (
        <p className="mt-1 text-xs text-zinc-500">From a cluster of {h.proposed.cluster.size} intents
          {h.proposed.cluster.cohesion != null ? ` · cohesion ${Number(h.proposed.cluster.cohesion).toFixed(2)}` : ""} · {h.proposed.cluster.method}</p>
      )}
    </li>
  );
}

export function NodeDetailEmpty() {
  return <Empty icon={<Sparkles />} title="Select a category" description="Click any node in the tree to see its description, supporting statements and revision history." />;
}
