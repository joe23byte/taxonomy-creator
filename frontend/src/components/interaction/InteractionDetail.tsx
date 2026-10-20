import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Ban, Check, ChevronDown, ChevronRight, Flag, History, Pencil, Quote, Sparkles, User, Headset,
} from "lucide-react";
import { api, type AssignmentFull, type IntentFull, type InteractionDetail as Detail, type TaxNode } from "@/lib/api";
import { cn, formatDateTime, sim, titleCase } from "@/lib/utils";
import { Button } from "../ui/button";
import { Badge, Select, Spinner, Textarea, Tip } from "../ui/primitives";
import { ReviewBadge, ClassificationBadge } from "./badges";
import { EVENT_META } from "../ActivityFeed";

export function InteractionDetail({ id, onOpenNode }: { id: number; onOpenNode?: (id: string) => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["interaction", id], queryFn: () => api.interaction(id) });
  const tax = useQuery({ queryKey: ["taxonomy", false], queryFn: () => api.taxonomy(false) });
  if (isLoading || !data) return <div className="flex h-full items-center justify-center text-zinc-400"><Spinner /></div>;
  return <Body d={data} nodes={tax.data?.nodes ?? []} onOpenNode={onOpenNode} />;
}

const METHOD_LABEL: Record<string, string> = {
  llm_extraction: "LLM extraction (L1/L2 only)",
  embedding_match: "Embedding match to category centroid",
  cluster: "Member of discovered cluster",
  llm_cluster_match: "Cluster matched to existing category by LLM",
  llm_outlier: "Rare intent placed by LLM",
  merge: "Moved by approved merge",
  split: "Moved by approved split",
  manual: "Manual correction",
  candidate: "Returned to candidate pool",
};

function Body({ d, nodes, onOpenNode }: { d: Detail; nodes: TaxNode[]; onOpenNode?: (id: string) => void }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState(d.reviewer_notes ?? "");
  useEffect(() => setNotes(d.reviewer_notes ?? ""), [d.id, d.reviewer_notes]);
  const refresh = () => ["interaction", "interactions", "summary", "taxonomy", "node"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const review = useMutation({
    mutationFn: (b: { flag?: boolean; unclassified?: boolean; notes?: string }) => api.reviewInteraction(d.id, b),
    onSuccess: refresh,
  });
  const evidence = useMemo(() => d.intents.map((i) => i.evidence).filter(Boolean) as string[], [d.intents]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-zinc-100 px-6 pb-4 pt-5 pr-12">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-base font-semibold text-zinc-900">{d.conversation_id}</h2>
          <ClassificationBadge status={d.classification_status} />
          <ReviewBadge status={d.review_status} />
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-500">
          {d.channel && <span>{titleCase(d.channel)}</span>}
          {d.segment && <span className="capitalize">{d.segment}</span>}
          {d.queue && <span>{d.queue}</span>}
          {d.timestamp && <span>{formatDateTime(d.timestamp)}</span>}
          {d.processed_order && <span>Analysed #{d.processed_order} · batch {(d.batch_index ?? 0) + 1}</span>}
        </div>
        {d.summary && <p className="mt-3 text-sm text-zinc-700">{d.summary}</p>}
        {d.no_intent_reason && <p className="mt-2 text-xs text-amber-700">No intent: {d.no_intent_reason}</p>}
        {d.error && <p className="mt-2 text-xs text-red-600">{d.error}</p>}
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Button size="xs" variant={d.review_flag ? "default" : "secondary"} onClick={() => review.mutate({ flag: !d.review_flag })}>
            <Flag />{d.review_flag ? "Flagged for review" : "Mark for review"}
          </Button>
          <Button size="xs" variant={d.review_unclassified ? "default" : "secondary"} onClick={() => review.mutate({ unclassified: !d.review_unclassified })}>
            <Ban />{d.review_unclassified ? "Unclassified" : "Mark as unclassified"}
          </Button>
        </div>
      </header>

      <div className="scroll-thin grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[1fr_1fr]">
        <section className="border-zinc-100 px-6 py-5 lg:border-r">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-400">Transcript</h3>
          <ol className="space-y-2.5">
            {d.turns.map((t, i) => (
              <li key={i} className={cn("flex gap-2", t.speaker === "customer" ? "" : "flex-row-reverse")}>
                <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
                  t.speaker === "customer" ? "bg-blue-50 text-blue-600" : "bg-zinc-100 text-zinc-500")}>
                  {t.speaker === "customer" ? <User className="size-3" /> : <Headset className="size-3" />}
                </span>
                <p className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-relaxed",
                  t.speaker === "customer" ? "rounded-tl-sm bg-white text-zinc-800 ring-1 ring-zinc-200" : "rounded-tr-sm bg-zinc-50 text-zinc-600")}>
                  {t.speaker === "customer" ? highlight(t.text, evidence) : t.text}
                </p>
              </li>
            ))}
          </ol>
          <div className="mt-6">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Reviewer notes</h3>
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add a note for this interaction…" />
            {notes !== (d.reviewer_notes ?? "") && (
              <Button size="xs" className="mt-2" onClick={() => review.mutate({ notes })}>Save note</Button>
            )}
          </div>
          {d.events.length > 0 && <ProcessingLog d={d} />}
        </section>

        <section className="space-y-3 bg-zinc-50/40 px-6 py-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
            Extracted intents {d.intents.length > 0 && <span className="text-zinc-400">({d.intents.length})</span>}
          </h3>
          {d.intents.length === 0 && (
            <p className="text-sm text-zinc-500">{d.status === "processed" ? "The model found no actionable customer intent." : "Not analysed yet."}</p>
          )}
          {d.intents.map((it) => <IntentCard key={it.id} intent={it} nodes={nodes} onChanged={refresh} onOpenNode={onOpenNode} />)}
        </section>
      </div>
    </div>
  );
}

function highlight(text: string, quotes: string[]) {
  const q = quotes.map((x) => x.trim()).filter((x) => x.length > 6).find((x) => text.toLowerCase().includes(x.toLowerCase()));
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  return <>{text.slice(0, i)}<mark className="evidence">{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>;
}

function Path({ a, onOpenNode }: { a: AssignmentFull; onOpenNode?: (id: string) => void }) {
  const parts = [1, 2, 3, 4].map((l) => ({
    level: l,
    id: (a as any)[`l${l}_id`] as string | null,
    label: (a as any)[`l${l}_label`] as string | null,
    status: (a as any)[`l${l}_status`] as string | null,
  }));
  return (
    <div className="flex flex-wrap items-center gap-1">
      {parts.map((p, i) => (
        <span key={p.level} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="size-3 text-zinc-300" />}
          {p.id ? (
            <button onClick={() => onOpenNode?.(p.id!)}
              className={cn("rounded px-1.5 py-0.5 text-xs cursor-pointer",
                p.level <= 2 ? "bg-zinc-100 text-zinc-700 hover:bg-zinc-200" : "bg-blue-50 text-blue-700 hover:bg-blue-100",
                p.status && p.status !== "active" && "line-through opacity-60")}>
              {p.label}
            </button>
          ) : (
            <span className="rounded border border-dashed border-zinc-200 px-1.5 py-0.5 text-xs text-zinc-400">L{p.level} —</span>
          )}
        </span>
      ))}
    </div>
  );
}

function IntentCard({ intent, nodes, onChanged, onOpenNode }: {
  intent: IntentFull; nodes: TaxNode[]; onChanged: () => void; onOpenNode?: (id: string) => void;
}) {
  const a = intent.assignment;
  const [editing, setEditing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: (b: { action: string; path?: Record<string, string | null>; notes?: string }) => api.reviewAssignment(a!.id, b),
    onSuccess: () => { setEditing(false); setErr(null); onChanged(); },
    onError: (e: Error) => setErr(e.message),
  });
  if (!a) return null;
  const verified = intent.evidence_verified;
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-zinc-900">{intent.intent_text}</p>
        <ReviewBadge status={a.review_status === "pending" && a.needs_review ? "needs_review" : a.review_status} />
      </div>
      {intent.evidence && (
        <div className="mt-2 flex items-start gap-1.5 text-[13px] text-zinc-600">
          <Quote className="mt-0.5 size-3 shrink-0 text-zinc-300" />
          <span className="italic">{intent.evidence}</span>
          <Tip content={verified === 2 ? "Quote found verbatim in a customer turn" : verified === 1 ? "Quote approximately matches the transcript" : "Quote not found in the transcript — check manually"}>
            <span className="shrink-0"><Badge tone={verified === 2 ? "green" : verified === 1 ? "neutral" : "amber"}>{verified === 2 ? "verbatim" : verified === 1 ? "approx." : "not found"}</Badge></span>
          </Tip>
        </div>
      )}
      <div className="mt-3"><Path a={a} onOpenNode={onOpenNode} /></div>

      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-zinc-400">Method</dt>
        <dd className="text-zinc-700">{METHOD_LABEL[a.method] ?? a.method}</dd>
        <dt className="text-zinc-400">Similarity</dt>
        <dd className="text-zinc-700">
          {a.similarity != null ? (
            <Tip content="Cosine similarity between this intent's embedding and the centroid of the assigned (or closest) L4 category. Not a probability.">
              <span className="font-mono">{sim(a.similarity)} cosine</span>
            </Tip>
          ) : <span className="text-zinc-400">not applicable</span>}
        </dd>
        {a.review_reason && (<><dt className="text-zinc-400">Review</dt><dd className="flex items-center gap-1 text-amber-700"><AlertTriangle className="size-3" />{a.review_reason}</dd></>)}
        {intent.reasoning && (<><dt className="text-zinc-400">AI reasoning</dt><dd className="text-zinc-600">{intent.reasoning}</dd></>)}
      </dl>

      {a.alternatives.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-medium text-zinc-400">{a.l4_id ? "Alternative categories" : "Closest categories"}</p>
          <div className="flex flex-wrap gap-1.5">
            {a.alternatives.filter((x) => x.node_id !== a.l4_id).map((x) => (
              <button key={x.node_id} onClick={() => onOpenNode?.(x.node_id)}
                className="rounded-md border border-zinc-200 px-1.5 py-0.5 text-xs text-zinc-600 hover:bg-zinc-50 cursor-pointer">
                {x.label ?? x.node_id} <span className="font-mono text-zinc-400">{x.similarity.toFixed(2)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {a.reviewer_notes && <p className="mt-2 rounded-md bg-zinc-50 px-2 py-1.5 text-xs text-zinc-600">Note: {a.reviewer_notes}</p>}

      {editing ? (
        <CorrectionEditor a={a} nodes={nodes} busy={act.isPending} onCancel={() => setEditing(false)}
          onSave={(path, notes) => act.mutate({ action: "correct", path, notes })} />
      ) : (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Button size="xs" variant="success" disabled={!a.l2_id || a.review_status === "confirmed"} onClick={() => act.mutate({ action: "confirm" })}><Check />Confirm</Button>
          <Button size="xs" variant="secondary" onClick={() => setEditing(true)}><Pencil />Correct</Button>
          <Button size="xs" variant="secondary" disabled={a.review_status === "unclassified"} onClick={() => act.mutate({ action: "unclassify" })}><Ban />Unclassified</Button>
          {a.review_status !== "pending" && <Button size="xs" variant="ghost" onClick={() => act.mutate({ action: "reset" })}>Reset</Button>}
        </div>
      )}
      {err && <p className="mt-2 text-xs text-red-600">{err}</p>}

      <button className="mt-3 flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-700 cursor-pointer" onClick={() => setShowHistory((s) => !s)}>
        {showHistory ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}<History className="size-3" /> Audit history ({a.history.length})
      </button>
      {showHistory && (
        <ol className="mt-2 space-y-1.5 border-l border-zinc-200 pl-3">
          {a.ai_original && (
            <li className="text-[11px] text-zinc-500">
              <span className="font-medium text-zinc-600">Latest AI assignment:</span>{" "}
              {[a.ai_original.l1_label, a.ai_original.l2_label, a.ai_original.l3_label, a.ai_original.l4_label].filter(Boolean).join(" › ") || "—"}
            </li>
          )}
          {a.history.map((h) => (
            <li key={h.id} className="text-[11px] text-zinc-500">
              <span className={cn("font-medium", h.actor === "user" ? "text-blue-700" : "text-zinc-600")}>{h.actor === "user" ? "Reviewer" : "AI"}</span>{" "}
              {h.action.replace(/_/g, " ")} · {formatDateTime(h.created_at)}
              {h.after?.l4_id !== h.before?.l4_id && h.after && <span className="font-mono"> · L4 {h.before?.l4_id ?? "—"} → {h.after?.l4_id ?? "—"}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function CorrectionEditor({ a, nodes, busy, onCancel, onSave }: {
  a: AssignmentFull; nodes: TaxNode[]; busy: boolean; onCancel: () => void; onSave: (path: Record<string, string | null>, notes?: string) => void;
}) {
  const active = nodes.filter((n) => n.status === "active");
  const [l1, setL1] = useState(a.l1_id ?? "");
  const [l2, setL2] = useState(a.l2_id ?? "");
  const [l3, setL3] = useState(a.l3_id ?? "");
  const [l4, setL4] = useState(a.l4_id ?? "");
  const [notes, setNotes] = useState(a.reviewer_notes ?? "");
  const opts = (level: number, parent: string) => active.filter((n) => n.level === level && n.parent_id === parent);
  return (
    <div className="mt-3 space-y-2 rounded-lg border border-blue-100 bg-blue-50/40 p-3">
      <p className="flex items-center gap-1 text-xs font-medium text-zinc-700"><Sparkles className="size-3 text-blue-500" />Correct the taxonomy path</p>
      <div className="grid grid-cols-2 gap-2">
        <Select value={l1} onChange={(e) => { setL1(e.target.value); setL2(""); setL3(""); setL4(""); }}>
          <option value="">L1…</option>
          {active.filter((n) => n.level === 1).map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </Select>
        <Select value={l2} disabled={!l1} onChange={(e) => { setL2(e.target.value); setL3(""); setL4(""); }}>
          <option value="">L2…</option>
          {opts(2, l1).map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </Select>
        <Select value={l3} disabled={!l2} onChange={(e) => { setL3(e.target.value); setL4(""); }}>
          <option value="">L3 (optional)</option>
          {opts(3, l2).map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </Select>
        <Select value={l4} disabled={!l3} onChange={(e) => setL4(e.target.value)}>
          <option value="">L4 (optional)</option>
          {opts(4, l3).map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </Select>
      </div>
      <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reviewer note (optional)" />
      <div className="flex gap-1.5">
        <Button size="xs" disabled={!l2 || busy} onClick={() => onSave({ l1_id: l1 || null, l2_id: l2 || null, l3_id: l3 || null, l4_id: l4 || null }, notes || undefined)}>
          Save correction
        </Button>
        <Button size="xs" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

function ProcessingLog({ d }: { d: Detail }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-6">
      <button className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-zinc-400 hover:text-zinc-700 cursor-pointer" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />} Processing log ({d.events.length})
      </button>
      {open && (
        <ol className="mt-2 space-y-1">
          {d.events.map((e) => {
            const Icon = (EVENT_META[e.kind] ?? EVENT_META.info).icon;
            return (
              <li key={e.id} className="flex items-start gap-2 text-xs text-zinc-600">
                <Icon className="mt-0.5 size-3 shrink-0 text-zinc-400" />{e.message.replace(`Interaction ${d.conversation_id} — `, "")}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
