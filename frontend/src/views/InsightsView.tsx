import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Info } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { DiscoveryCurve } from "@/components/DiscoveryCurve";
import { Badge, Card, CardHeader, Empty } from "@/components/ui/primitives";

export function InsightsView({ summary, openNode }: { summary: Summary | undefined; openNode: (id: string) => void }) {
  const curve = useQuery({ queryKey: ["curve"], queryFn: api.curve });
  const evaluation = useQuery({ queryKey: ["evaluation", summary?.processed, summary?.taxonomy_version], queryFn: api.evaluation });
  const overlaps = useQuery({ queryKey: ["proposals", "proposed"], queryFn: () => api.proposals("proposed") });
  const merges = (overlaps.data ?? []).filter((p) => p.change_type === "merge");
  const ev = evaluation.data;
  const metrics = summary ? [
    ["Processed interactions", summary.processed],
    ["Unique discovered intents (L4)", summary.discovered_intents],
    ["L3 categories", summary.l3_nodes],
    ["Unclassified interactions", summary.unclassified],
    ["Open candidates (no L4 yet)", summary.open_candidates],
    ["Overlapping categories", summary.overlapping_categories],
  ] : [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">Evaluation & progress</h1>
        <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500">
          <Info className="size-3" />A flattening curve suggests saturation for this dataset only — it is not proof of taxonomy completeness.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([l, v]) => (
          <Card key={l as string} className="px-4 py-3">
            <p className="text-xs text-zinc-500">{l}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-zinc-900">{v}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title="Intent discovery curve" description="Distinct L4 categories (current taxonomy) observed within the first N analysed interactions." />
          <div className="px-4 pb-4"><DiscoveryCurve curve={curve.data} height={220} /></div>
        </Card>
        <Card>
          <CardHeader title="New intents per processing batch" />
          <div className="scroll-thin max-h-[260px] overflow-auto px-2 pb-3">
            {!curve.data?.batches.length ? <p className="px-3 pb-3 text-xs text-zinc-400">No batch refinements yet.</p> : (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-zinc-400">
                  {["Batch", "Analysed", "Intents", "New L3", "New L4", "Total L4", "Proposals"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}
                </tr></thead>
                <tbody>
                  {curve.data.batches.map((b, i) => (
                    <tr key={i} className="border-t border-zinc-100 tabular-nums text-zinc-700">
                      <td className="px-2 py-1.5">{i + 1}</td>
                      <td className="px-2 py-1.5">{b.processed_total}</td>
                      <td className="px-2 py-1.5">{b.intents_extracted}</td>
                      <td className="px-2 py-1.5">{b.new_l3}</td>
                      <td className="px-2 py-1.5 font-medium text-blue-700">{b.new_l4}</td>
                      <td className="px-2 py-1.5">{b.total_l4}</td>
                      <td className="px-2 py-1.5">{b.proposals_created}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </div>

      {merges.length > 0 && (
        <Card>
          <CardHeader title="Duplicate & overlapping categories" description="Pending merge proposals based on embedding centroid similarity." />
          <ul className="px-5 pb-4 space-y-1.5">
            {merges.map((m) => (
              <li key={m.id} className="flex items-center gap-2 text-[13px]">
                <button className="text-blue-700 hover:underline cursor-pointer" onClick={() => openNode(m.proposed.source_id)}>{m.proposed.source_label}</button>
                <span className="text-zinc-400">≈</span>
                <button className="text-blue-700 hover:underline cursor-pointer" onClick={() => openNode(m.proposed.target_id)}>{m.proposed.target_label}</button>
                <span className="ml-auto font-mono text-xs text-zinc-500">{Number(m.proposed.similarity).toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title={<span className="flex items-center gap-1.5"><FlaskConical className="size-3.5 text-violet-500" />Comparison with synthetic ground truth</span>}
          description="Loaded only here for evaluation — the analysis pipeline never sees these labels." />
        <div className="px-5 pb-5">
          {!ev?.available ? <Empty title="No ground truth available" description="Only the synthetic sample dataset ships with labels." /> :
            !ev.evaluated ? <p className="text-xs text-zinc-400">Analyse sample interactions to compare.</p> : (
              <>
                <div className="mb-4 flex flex-wrap gap-6 text-sm">
                  <Stat label="Evaluated conversations" value={ev.evaluated} />
                  <Stat label="Ground-truth intent types" value={ev.ground_truth_types} />
                  <Stat label="Discovered L4 used" value={ev.discovered_l4} />
                  <Stat label="L2 recall" value={ev.l2_recall != null ? `${Math.round(ev.l2_recall * 100)}%` : "—"} hint="Share of true intents whose expected L2 was assigned in the conversation" />
                  <Stat label="L4 purity" value={ev.l4_purity != null ? `${Math.round(ev.l4_purity * 100)}%` : "—"} hint="Share of conversations in each L4 that share its dominant true intent" />
                </div>
                <div className="scroll-thin max-h-[380px] overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-white"><tr className="text-left text-zinc-400">
                      <th className="px-2 py-1.5 font-medium">True intent (hidden from AI)</th>
                      <th className="px-2 py-1.5 font-medium">Conversations</th>
                      <th className="px-2 py-1.5 font-medium">Mostly assigned to</th>
                      <th className="px-2 py-1.5 font-medium">Distinct L4</th>
                    </tr></thead>
                    <tbody>
                      {ev.types?.map((t) => (
                        <tr key={t.key} className="border-t border-zinc-100 text-zinc-700">
                          <td className="px-2 py-1.5 font-medium">{t.label}</td>
                          <td className="px-2 py-1.5 tabular-nums">{t.conversations}</td>
                          <td className="px-2 py-1.5">
                            {t.top_categories.length ? t.top_categories.map((c) => (
                              <button key={c.id} onClick={() => openNode(c.id)} className="mr-1.5 cursor-pointer"><Badge tone="blue">{c.label} · {c.conversations}</Badge></button>
                            )) : <span className="text-zinc-400">not yet in an L4</span>}
                          </td>
                          <td className="px-2 py-1.5 tabular-nums">{t.distinct_categories}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[11px] text-zinc-400">{ev.note}</p>
              </>
            )}
        </div>
      </Card>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div title={hint}>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-zinc-900">{value}</p>
    </div>
  );
}
