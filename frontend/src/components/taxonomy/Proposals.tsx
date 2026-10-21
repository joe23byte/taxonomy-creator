import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, GitBranchPlus, GitMerge, PenLine, Split, X, ArrowRightLeft, Archive, Pencil } from "lucide-react";
import { api, type Change } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, timeAgo } from "@/lib/utils";
import { Button } from "../ui/button";
import { Badge, Empty, Spinner } from "../ui/primitives";

const ICON = { create: GitBranchPlus, merge: GitMerge, split: Split, refine: PenLine, update: Pencil, move: ArrowRightLeft, retire: Archive };

export function Proposals({ onSelectNode }: { onSelectNode: (id: string) => void }) {
  const { t } = useI18n();
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
            {v === "pending" ? `${t("proposals.awaiting")}${pending.data ? ` (${pending.data.length})` : ""}` : t("proposals.all")}
          </button>
        ))}
      </div>
      {error && <p className="mx-4 mb-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-4 pb-4">
        {!items ? (
          <div className="flex justify-center py-8 text-zinc-400"><Spinner /></div>
        ) : items.length === 0 ? (
          <Empty icon={<Check />} title={view === "pending" ? t("proposals.emptyPending") : t("proposals.emptyHistory")}
            description={view === "pending" ? t("proposals.emptyPendingText") : undefined} />
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

// "{a}"/"{b}" placeholders are rendered bold
function Rich({ text, a, b }: { text: string; a?: string; b?: string }) {
  return <>{text.split(/(\{[ab]\})/).map((part, i) => part === "{a}" ? <b key={i}>{a}</b> : part === "{b}" ? <b key={i}>{b}</b> : part)}</>;
}

function Title({ c }: { c: Change }) {
  const { t } = useI18n();
  const p = c.proposed ?? {};
  switch (c.change_type) {
    case "create":
      if (!p.l4) return <Rich text={t("proposals.title.created")} a={p.label} />;
      return p.l3?.is_new
        ? <Rich text={t("proposals.title.newUnderNewL3")} a={p.l4.label} b={p.l3.label} />
        : <>{<Rich text={t("proposals.title.newUnder")} a={p.l4.label} />} {p.l3?.label}</>;
    case "merge":
      return <Rich text={t("proposals.title.merge")} a={p.source_label} b={p.target_label} />;
    case "split":
      return <><Rich text={t("proposals.title.split")} a={p.source_label} /> {p.parts?.map((x: any) => x.label).join(", ")}</>;
    case "refine":
      return <>{t("changeType.refine")}</>;
    case "update":
      return <Rich text={t("proposals.title.edited")} a={p.label} />;
    case "move":
      return <>{t("proposals.title.moved", { parent: p.parent_id })}</>;
    case "retire":
      return <>{t("proposals.title.retired")}</>;
  }
  return null;
}

function ProposalCard({ c, busy, onAccept, onReject, onSelectNode }: {
  c: Change; busy: boolean; onAccept: () => void; onReject: () => void; onSelectNode: (id: string) => void;
}) {
  const { t, lang } = useI18n();
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
          <p className="text-[13px] leading-5 text-zinc-800 [&_b]:font-semibold"><Title c={c} /></p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
            <Badge tone={pending ? "amber" : c.status === "rejected" ? "neutral" : "green"}>{t(`changeStatus.${c.status}`)}</Badge>
            <Badge tone="outline">{c.source === "ai" ? t("common.ai") : t("common.user")}</Badge>
            {c.node_id && <button className="font-mono hover:text-blue-600 cursor-pointer" onClick={() => onSelectNode(c.node_id!)}>{c.node_id}</button>}
            <span>{timeAgo(c.created_at, lang)}</span>
          </div>
          {c.rationale && <p className="mt-1.5 text-xs text-zinc-500">{c.rationale}</p>}
          {p.conflict && (
            <p className="mt-1.5 flex items-start gap-1 text-xs text-amber-700"><AlertTriangle className="mt-px size-3 shrink-0" />{p.conflict}</p>
          )}
          {p.cluster && (
            <div className="mt-2 rounded-lg bg-zinc-50 px-2.5 py-2">
              <p className="text-[11px] text-zinc-500">
                {t("common.intents", { count: p.cluster.size })}{p.cluster.cohesion != null ? ` · ${t("common.cohesion")} ${Number(p.cluster.cohesion).toFixed(2)}` : ""} · {p.cluster.method}
              </p>
              <ul className="mt-1 space-y-0.5">
                {(p.cluster.examples ?? []).slice(0, 4).map((x: string, i: number) => <li key={i} className="truncate text-xs text-zinc-700">• {x}</li>)}
              </ul>
            </div>
          )}
          {c.change_type === "split" && p.parts && (
            <ul className="mt-2 space-y-1">
              {p.parts.map((part: any) => <li key={part.group} className="text-xs text-zinc-600"><b className="font-medium text-zinc-800">{part.label}</b> — {t("common.intents", { count: part.member_intent_ids?.length ?? 0 })}</li>)}
            </ul>
          )}
          {c.change_type === "merge" && p.similarity != null && (
            <p className="mt-1.5 text-xs text-zinc-500">{t("proposals.mergeHint", { sim: Number(p.similarity).toFixed(2) })}</p>
          )}
          {pending && (
            <div className="mt-3 flex gap-1.5">
              <Button size="xs" variant="success" disabled={busy} onClick={onAccept}><Check />{t("proposals.approve")}</Button>
              <Button size="xs" variant="secondary" disabled={busy} onClick={onReject}><X />{t("proposals.reject")}</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
