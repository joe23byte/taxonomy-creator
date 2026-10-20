import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { api, type InteractionRow } from "@/lib/api";
import { cn, titleCase } from "@/lib/utils";
import { ClassificationBadge, CLASS_LABELS, ReviewBadge, REVIEW_LABELS } from "@/components/interaction/badges";
import { Card, Empty, Input, Select, Spinner } from "@/components/ui/primitives";

type SortKey = "conversation_id" | "channel" | "segment" | "summary" | "l1" | "l2" | "l3" | "l4" | "classification_status" | "review_status";

const COLS: { key: SortKey; label: string; className?: string }[] = [
  { key: "conversation_id", label: "Conversation", className: "w-[118px]" },
  { key: "channel", label: "Channel", className: "w-[104px]" },
  { key: "segment", label: "Segment", className: "w-[80px]" },
  { key: "summary", label: "Customer intent summary", className: "min-w-[220px]" },
  { key: "l1", label: "L1", className: "w-[130px]" },
  { key: "l2", label: "L2", className: "w-[140px]" },
  { key: "l3", label: "L3", className: "w-[140px]" },
  { key: "l4", label: "L4", className: "w-[160px]" },
  { key: "classification_status", label: "Classification", className: "w-[110px]" },
  { key: "review_status", label: "Review", className: "w-[110px]" },
];

function sortValue(r: InteractionRow, k: SortKey): string {
  if (k === "l1" || k === "l2" || k === "l3" || k === "l4") return r.assignments.map((a) => (a as any)[`${k}_label`] ?? "").join(" ") || "~";
  if (k === "summary") return r.summary ?? r.assignments.map((a) => a.intent_text).join(" ");
  return String((r as any)[k] ?? "~");
}

export function InteractionsView({ openInteraction }: { openInteraction: (id: number) => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["interactions"], queryFn: api.interactions });
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [review, setReview] = useState("");
  const [klass, setKlass] = useState("");
  const [l1, setL1] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "conversation_id", dir: 1 });

  const rows = data ?? [];
  const l1s = useMemo(() => [...new Map(rows.flatMap((r) => r.assignments).filter((a) => a.l1_id).map((a) => [a.l1_id!, a.l1_label!])).entries()], [rows]);
  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim();
    return rows.filter((r) =>
      (!channel || r.channel === channel) &&
      (!review || r.review_status === review) &&
      (!klass || r.classification_status === klass) &&
      (!l1 || r.assignments.some((a) => a.l1_id === l1)) &&
      (!needle || [r.conversation_id, r.summary, r.queue, ...r.assignments.flatMap((a) => [a.intent_text, a.l2_label, a.l3_label, a.l4_label])]
        .some((v) => v?.toLowerCase().includes(needle))),
    ).sort((a, b) => sortValue(a, sort.key).localeCompare(sortValue(b, sort.key), undefined, { numeric: true }) * sort.dir);
  }, [rows, q, channel, review, klass, l1, sort]);
  const channels = [...new Set(rows.map((r) => r.channel).filter(Boolean))] as string[];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">Interactions & review</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            {filtered.length} of {rows.length} interactions · {rows.reduce((n, r) => n + r.assignments.length, 0)} intent assignments
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search ID, intent, category…" className="h-8 pl-8 text-[13px]" />
        </div>
        <Filter value={channel} onChange={setChannel} label="All channels" options={channels.map((c) => [c, titleCase(c)])} />
        <Filter value={l1} onChange={setL1} label="All L1" options={l1s} />
        <Filter value={klass} onChange={setKlass} label="Any classification" options={Object.entries(CLASS_LABELS)} />
        <Filter value={review} onChange={setReview} label="Any review status" options={Object.entries(REVIEW_LABELS)} />
      </div>

      <Card className="overflow-hidden">
        {isLoading ? <div className="flex h-40 items-center justify-center text-zinc-400"><Spinner /></div> : rows.length === 0 ? (
          <Empty title="No interactions yet" description="Import data or load the sample dataset from the Workspace." />
        ) : (
          <div className="scroll-thin max-h-[calc(100vh-230px)] overflow-auto">
            <table className="w-full min-w-[1300px] border-collapse text-[13px]">
              <thead className="sticky top-0 z-10 bg-zinc-50/95 backdrop-blur">
                <tr className="border-b border-zinc-200">
                  {COLS.map((c) => (
                    <th key={c.key} className={cn("px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-zinc-500", c.className)}>
                      <button className="flex items-center gap-1 hover:text-zinc-800 cursor-pointer" onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
                        {c.label}
                        {sort.key === c.key && (sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} onClick={() => openInteraction(r.id)} className="cursor-pointer border-b border-zinc-100 align-top transition hover:bg-blue-50/30">
                    <td className="px-3 py-2.5 font-mono text-xs font-medium text-zinc-800">{r.conversation_id}</td>
                    <td className="px-3 py-2.5 text-zinc-600">{titleCase(r.channel) || "—"}</td>
                    <td className="px-3 py-2.5 capitalize text-zinc-600">{r.segment ?? "—"}</td>
                    <td className="px-3 py-2.5">
                      {r.assignments.length ? (
                        <ul className="space-y-1">{r.assignments.map((a) => <li key={a.id} className="text-zinc-800">{a.intent_text}</li>)}</ul>
                      ) : <span className="text-zinc-400">{r.summary ?? (r.status === "processed" ? "No intent found" : "—")}</span>}
                    </td>
                    {(["l1", "l2", "l3", "l4"] as const).map((lvl) => (
                      <td key={lvl} className="px-3 py-2.5">
                        <ul className="space-y-1">
                          {r.assignments.map((a) => {
                            const label = (a as any)[`${lvl}_label`] as string | null;
                            return (
                              <li key={a.id} className={cn("truncate", label ? (lvl === "l3" || lvl === "l4" ? "text-blue-700" : "text-zinc-700") : "text-zinc-300", a.review_status === "unclassified" && "line-through opacity-50")}>
                                {label ?? "—"}
                              </li>
                            );
                          })}
                        </ul>
                      </td>
                    ))}
                    <td className="px-3 py-2.5"><ClassificationBadge status={r.classification_status} /></td>
                    <td className="px-3 py-2.5"><ReviewBadge status={r.review_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Filter({ value, onChange, label, options }: { value: string; onChange: (v: string) => void; label: string; options: [string, string][] }) {
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} className={cn("h-8 w-auto text-[13px]", value && "border-blue-300 text-blue-700")}>
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </Select>
  );
}
