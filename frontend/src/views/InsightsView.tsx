import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Info } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { DiscoveryCurve } from "@/components/DiscoveryCurve";
import { TopIntents } from "@/components/insights/TopIntents";
import { ConcentrationKpis, CoverageCurve, IntentDonut } from "@/components/insights/IntentMix";
import { OverlapChart } from "@/components/insights/OverlapChart";
import { Badge, Card, CardHeader } from "@/components/ui/primitives";
import type { NavOptions } from "@/App";

export function InsightsView({ summary, openNode, go }: {
  summary: Summary | undefined;
  openNode: (id: string) => void;
  go: (view: string, opts?: NavOptions) => void;
}) {
  const openProposals = () => go("taxonomy", { panel: "proposals" });
  const { t, pct, lang } = useI18n();
  const curve = useQuery({ queryKey: ["curve"], queryFn: api.curve });
  const volume = useQuery({ queryKey: ["intent-volume", lang, summary?.processed, summary?.taxonomy_version], queryFn: () => api.intentVolume(lang) });
  const overlapPairs = useQuery({ queryKey: ["overlaps", summary?.processed, summary?.taxonomy_version], queryFn: api.overlaps });
  const running = !!summary?.worker_alive;
  const evaluation = useQuery({ queryKey: ["evaluation", summary?.processed, summary?.taxonomy_version], queryFn: api.evaluation });
  const overlaps = useQuery({ queryKey: ["proposals", "proposed"], queryFn: () => api.proposals("proposed") });
  const merges = (overlaps.data ?? []).filter((p) => p.change_type === "merge");
  const ev = evaluation.data;
  const metrics: [string, number, () => void][] = summary ? [
    [t("insights.metrics.processed"), summary.processed, () => go("interactions")],
    [t("insights.metrics.discovered"), summary.discovered_intents, () => go("taxonomy")],
    [t("insights.metrics.l3"), summary.l3_nodes, () => go("taxonomy")],
    [t("insights.metrics.unclassified"), summary.unclassified, () => go("interactions", { classification: "unclassified" })],
    [t("insights.metrics.open"), summary.open_candidates, () => go("interactions", { classification: "partial" })],
    [t("insights.metrics.overlapping"), summary.overlapping_categories, openProposals],
  ] : [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{t("nav.insights")}</h1>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([l, v, onClick]) => (
          <button key={l} onClick={onClick} className="rounded-xl border border-zinc-200/80 bg-white px-4 py-3 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition hover:border-zinc-300 cursor-pointer">
            <p className="text-xs text-zinc-500">{l}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-zinc-900">{v}</p>
          </button>
        ))}
      </div>

      <SectionTitle>{t("insights.sectionVolume")}</SectionTitle>
      <TopIntents data={volume.data} loadError={volume.isError} onRetry={() => volume.refetch()} analysisRunning={running} openNode={openNode} />
      {!!volume.data?.items.length && (
        <>
          <ConcentrationKpis data={volume.data} />
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.15fr]">
            <IntentDonut data={volume.data} openNode={openNode} />
            <CoverageCurve data={volume.data} />
          </div>
        </>
      )}

      <div>
        <SectionTitle>{t("insights.sectionQuality")}</SectionTitle>
        <p className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
          <Info className="size-3" />{t("insights.saturation")}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title={t("workspace.curveTitle")} description={t("insights.curveText")} />
          <div className="px-4 pb-4"><DiscoveryCurve curve={curve.data} height={220} /></div>
        </Card>
        <Card>
          <CardHeader title={t("insights.batches.title")} />
          <div className="scroll-thin max-h-[260px] overflow-auto px-2 pb-3">
            {!curve.data?.batches.length ? <p className="px-3 pb-3 text-xs text-zinc-400">{t("insights.batches.empty")}</p> : (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-zinc-400">
                  {["batch", "analysed", "intents", "newL3", "newL4", "totalL4", "proposals"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{t(`insights.batches.${h}`)}</th>)}
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

      <OverlapChart data={overlapPairs.data} openNode={openNode} openProposals={openProposals} />

      {merges.length > 0 && (
        <Card>
          <CardHeader title={t("insights.merges.title")} description={t("insights.merges.text")} />
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

      {ev?.available && !!ev.evaluated && (
      <Card>
        <CardHeader title={<span className="flex items-center gap-1.5"><FlaskConical className="size-3.5 text-violet-500" />{t("insights.gt.title")}</span>}
          description={t("insights.gt.text")} />
        <div className="px-5 pb-5">
              <>
                <div className="mb-4 flex flex-wrap gap-6 text-sm">
                  <Stat label={t("insights.gt.evaluated")} value={ev.evaluated} />
                  <Stat label={t("insights.gt.types")} value={ev.ground_truth_types} />
                  <Stat label={t("insights.gt.l4Used")} value={ev.discovered_l4} />
                  <Stat label={t("insights.gt.l2Recall")} value={ev.l2_recall != null ? pct(ev.l2_recall) : "—"} hint={t("insights.gt.l2RecallHint")} />
                  <Stat label={t("insights.gt.l4Purity")} value={ev.l4_purity != null ? pct(ev.l4_purity) : "—"} hint={t("insights.gt.l4PurityHint")} />
                </div>
                <div className="scroll-thin max-h-[380px] overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-white"><tr className="text-left text-zinc-400">
                      <th className="px-2 py-1.5 font-medium">{t("insights.gt.colTrue")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("insights.gt.colConversations")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("insights.gt.colAssigned")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("insights.gt.colDistinct")}</th>
                    </tr></thead>
                    <tbody>
                      {ev.types?.map((gt) => (
                        <tr key={gt.key} className="border-t border-zinc-100 text-zinc-700">
                          <td className="px-2 py-1.5 font-medium">{gt.label}</td>
                          <td className="px-2 py-1.5 tabular-nums">{gt.conversations}</td>
                          <td className="px-2 py-1.5">
                            {gt.top_categories.length ? gt.top_categories.map((c) => (
                              <button key={c.id} onClick={() => openNode(c.id)} className="mr-1.5 cursor-pointer"><Badge tone="blue">{c.label} · {c.conversations}</Badge></button>
                            )) : <span className="text-zinc-400">{t("insights.gt.notInL4")}</span>}
                          </td>
                          <td className="px-2 py-1.5 tabular-nums">{gt.distinct_categories}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[11px] text-zinc-400">{t("insights.gt.note")}</p>
              </>
        </div>
      </Card>
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{children}</h2>;
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div title={hint}>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-zinc-900">{value}</p>
    </div>
  );
}
