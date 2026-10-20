import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, GitBranchPlus, GitMerge, PenLine, Split, X, ArrowRightLeft, Archive, Pencil } from "lucide-react";
import { api, type Change } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { Button } from "../ui/button";
import { Badge, Empty, Spinner } from "../ui/primitives";

const ICON = { create: GitBranchPlus, merge: GitMerge, split: Split, refine: PenLine, update: Pencil, move: ArrowRightLeft, retire: Archive };

export function Proposals({ onSelectNode }: { onSelectNode: (id: string) => void }) {
  const [view, setView] = useState<"pending" | "history">("pending");
  const qc = useQueryClient();
  const pending = useQuery({ queryKey: ["proposals", "proposed"], queryFn: () => api.proposals("proposed") });
  const history = useQuery({ queryKey: ["changes"], queryFn: api.changes, enabled: view === "history" });
  const [error, setError] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) => (accept ? api.acceptProposal(id) : api.rejectProposal(id)),
    onSuccess: () => {
      setError(null);
      ["proposals", "changes", "taxonomy", "node", "summary", "interactions"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e: Error) => setError(e.message),
  });
  const items = view === "pending" ? pending.data : history.data;

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center gap-1.5 px-4 pb-3">
        {(["pending", "history"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={cn("rounded-md px-2 py-1 text-xs font-medium cursor-pointer", view === v ? "bg-zinc-900 text-white" : "text-zinc-500 hover:bg-zinc-100")}>
            {v === "pending" ? `Awaiting review${pending.data ? ` (${pending.data.length})` : ""}` : "All changes"}
          </button>
        ))}
      </div>
      {error && <p className="mx-4 mb-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-4 pb-4">
        {!items ? (
          <div className="flex justify-center py-8 text-zinc-400"><Spinner /></div>
        ) : items.length === 0 ? (
          <Empty icon={<Check />} title={view === "pending" ? "Nothing to review" : "No changes yet"}
            description={view === "pending" ? "Merges, splits and conflicting new categories proposed by the AI appear here." : undefined} />
        ) : (
          items.map((c) => (
            <ProposalCard key={c.id} c={c} busy={act.isPending && act.variables?.id === c.id}
              onAccept={() => act.mutate({ id: c.id, accept: true })} onReject={() => act.mutate({ id: c.id, accept: false })}
              onSelectNode={onSelectNode} />
          ))
        )}
      </div>
    </div>
  );
}

function title(c: Change) {
  const p = c.proposed ?? {};
  switch (c.change_type) {
    case "create":
      return p.l4 ? <>New category <b>{p.l4.label}</b> under {p.l3?.is_new ? <>new L3 <b>{p.l3.label}</b></> : p.l3?.label}</> : <>Created <b>{p.label}</b></>;
    case "merge":
      return <>Merge <b>{p.source_label}</b> into <b>{p.target_label}</b></>;
    case "split":
      return <>Split <b>{p.source_label}</b> into {p.parts?.map((x: any) => x.label).join(", ")}</>;
    case "refine":
      return <>Description refined</>;
    case "update":
      return <>Edited <b>{p.label}</b></>;
    case "move":
      return <>Moved to {p.parent_id}</>;
    case "retire":
      return <>Retired category</>;
  }
}

function ProposalCard({ c, busy, onAccept, onReject, onSelectNode }: {
  c: Change; busy: boolean; onAccept: () => void; onReject: () => void; onSelectNode: (id: string) => void;
}) {
  const Icon = ICON[c.change_type] ?? GitBranchPlus;
  const p = c.proposed ?? {};
  const pending = c.status === "proposed";
  return (
    <div className={cn("rounded-xl border bg-white p-3.5 animate-fade-in", pending ? "border-zinc-200 shadow-xs" : "border-zinc-100")}>
      <div className="flex items-start gap-2.5">
        <div className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md",
          c.change_type === "merge" || c.change_type === "split" ? "bg-amber-50 text-amber-600" : "bg-blue-50 text-blue-600")}>
          <Icon className="size-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-5 text-zinc-800 [&_b]:font-semibold">{title(c)}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
            <Badge tone={pending ? "amber" : c.status === "rejected" ? "neutral" : "green"}>{c.status.replace("_", " ")}</Badge>
            <Badge tone="outline">{c.source === "ai" ? "AI" : "User"}</Badge>
            {c.node_id && <button className="font-mono hover:text-blue-600 cursor-pointer" onClick={() => onSelectNode(c.node_id!)}>{c.node_id}</button>}
            <span>{timeAgo(c.created_at)}</span>
          </div>
          {c.rationale && <p className="mt-1.5 text-xs text-zinc-500">{c.rationale}</p>}
          {p.conflict && (
            <p className="mt-1.5 flex items-start gap-1 text-xs text-amber-700"><AlertTriangle className="mt-px size-3 shrink-0" />{p.conflict}</p>
          )}
          {p.cluster && (
            <div className="mt-2 rounded-lg bg-zinc-50 px-2.5 py-2">
              <p className="text-[11px] text-zinc-500">
                {p.cluster.size} intents{p.cluster.cohesion != null ? ` · cohesion ${Number(p.cluster.cohesion).toFixed(2)}` : ""} · {p.cluster.method}
              </p>
              <ul className="mt-1 space-y-0.5">
                {(p.cluster.examples ?? []).slice(0, 4).map((x: string, i: number) => <li key={i} className="truncate text-xs text-zinc-700">• {x}</li>)}
              </ul>
            </div>
          )}
          {c.change_type === "split" && p.parts && (
            <ul className="mt-2 space-y-1">
              {p.parts.map((part: any) => <li key={part.group} className="text-xs text-zinc-600"><b className="font-medium text-zinc-800">{part.label}</b> — {part.member_intent_ids?.length} intents</li>)}
            </ul>
          )}
          {c.change_type === "merge" && p.similarity != null && (
            <p className="mt-1.5 text-xs text-zinc-500">Centroid similarity {Number(p.similarity).toFixed(2)}. Unreviewed assignments will move; human-reviewed ones are preserved and flagged.</p>
          )}
          {pending && (
            <div className="mt-3 flex gap-1.5">
              <Button size="xs" variant="success" disabled={busy} onClick={onAccept}><Check />Approve</Button>
              <Button size="xs" variant="secondary" disabled={busy} onClick={onReject}><X />Reject</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
