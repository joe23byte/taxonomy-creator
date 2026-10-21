import type { Overlaps } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Badge, Card, CardHeader } from "@/components/ui/primitives";

const MIN = 0.5;

export function OverlapChart({ data, openNode, openProposals }: {
  data: Overlaps | undefined;
  openNode: (id: string) => void;
  openProposals: () => void;
}) {
  const { t } = useI18n();
  if (!data?.pairs.length) return null;
  const pos = (v: number) => `${Math.max(0, Math.min(1, (v - MIN) / (1 - MIN))) * 100}%`;
  const th = data.merge_threshold;
  return (
    <Card>
      <CardHeader title={t("insights.overlap.title")}
        description={t("insights.overlap.text", { n: data.compared, th: th.toFixed(2) })} />
      <div className="px-5 pb-5">
        <div className="mb-1 grid grid-cols-[minmax(0,1fr)_minmax(160px,1.1fr)_48px] gap-3 text-[10px] text-zinc-400">
          <span />
          <div className="relative h-3">
            {[0.5, 0.75, 1].map((v) => (
              <span key={v} className="absolute -translate-x-1/2" style={{ left: pos(v) }}>{v.toFixed(2)}</span>
            ))}
          </div>
          <span />
        </div>
        <ul className="space-y-1.5">
          {data.pairs.map((p) => {
            const above = p.similarity >= th;
            return (
              <li key={`${p.a.id}-${p.b.id}`} className="grid grid-cols-[minmax(0,1fr)_minmax(160px,1.1fr)_48px] items-center gap-3 text-[12.5px]">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 truncate">
                    <button className="truncate text-zinc-800 hover:text-blue-700 hover:underline cursor-pointer" onClick={() => openNode(p.a.id)}>{p.a.label}</button>
                    <span className="shrink-0 text-zinc-300">↔</span>
                    <button className="truncate text-zinc-800 hover:text-blue-700 hover:underline cursor-pointer" onClick={() => openNode(p.b.id)}>{p.b.label}</button>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                    {p.l2}{p.same_l3 && ` · ${t("insights.overlap.sameL3")}`}
                    {p.proposal_id != null && <button onClick={openProposals} className="cursor-pointer"><Badge tone="amber">{t("insights.overlap.proposed")}</Badge></button>}
                  </div>
                </div>
                <div className="relative h-3 rounded-full bg-zinc-100">
                  <div className={cn("absolute inset-y-0 left-0 rounded-full", above ? "bg-amber-500" : "bg-blue-500/70")} style={{ width: pos(p.similarity) }} />
                  <div className="absolute -inset-y-1 w-px bg-amber-600" style={{ left: pos(th) }} title={`${t("insights.overlap.threshold")} ${th.toFixed(2)}`} />
                </div>
                <span className={cn("text-right font-mono text-xs tabular-nums", above ? "font-semibold text-amber-700" : "text-zinc-500")}>{p.similarity.toFixed(2)}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-zinc-400">
          <span className="inline-block h-3 w-px bg-amber-600" />{t("insights.overlap.legend")}
        </p>
      </div>
    </Card>
  );
}
