import { useState } from "react";
import type { IntentVolume } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Card, CardHeader } from "@/components/ui/primitives";

const TOP_COLORS = ["#2563eb", "#7c3aed", "#0d9488", "#d97706", "#e11d48", "#0891b2", "#65a30d", "#c026d3"];
const OTHER_COLOR = "#d4d4d8";
const NONE_COLOR = "#f4f4f5";

export function ConcentrationKpis({ data }: { data: IntentVolume }) {
  const { t, pct, lang } = useI18n();
  const k = data.kpis;
  const tiles: [string, string, string, string?][] = [
    [t("insights.kpi.topCover", { n: data.top_n }), pct(k.top_coverage), t("insights.kpi.topCoverSub"), t("insights.kpi.topCoverHint")],
    [t("insights.kpi.for80"), k.intents_for_80 != null ? t("insights.kpi.nOf", { n: k.intents_for_80, total: k.active_l4 }) : "—",
      t("insights.kpi.for80Sub"), t("insights.kpi.for80Hint")],
    [t("insights.kpi.longTail"), String(k.long_tail), t("insights.kpi.longTailSub", { n: k.long_tail_max }), t("insights.kpi.longTailHint")],
    [t("insights.kpi.multi"), pct(k.multi_intent_share), t("insights.kpi.multiSub", { n: k.avg_intents.toLocaleString(lang, { maximumFractionDigits: 1, minimumFractionDigits: 1 }) })],
    [t("insights.kpi.classified"), pct(k.classified_share), t("insights.kpi.classifiedSub", { n: k.classified_interactions })],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {tiles.map(([label, value, sub, hint]) => (
        <Card key={label} className="px-4 py-3" title={hint}>
          <p className="text-xs text-zinc-500">{label}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-zinc-900">{value}</p>
          <p className="text-[11px] text-zinc-400">{sub}</p>
        </Card>
      ))}
    </div>
  );
}

export function IntentDonut({ data, openNode }: { data: IntentVolume; openNode: (id: string) => void }) {
  const { t, pct } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const total = data.mix.reduce((n, m) => n + m.intents, 0);
  let topIdx = 0;
  const segments = data.mix.map((m) => ({
    ...m,
    label: m.kind === "other" ? t("insights.donut.other", { n: m.count ?? 0 }) : m.kind === "none" ? t("insights.donut.none") : m.label,
    color: m.id ? TOP_COLORS[topIdx++ % TOP_COLORS.length] : m.kind === "other" ? OTHER_COLOR : NONE_COLOR,
    share: total ? m.intents / total : 0,
  }));
  const R = 70, STROKE = 26, C = 2 * Math.PI * R;
  let offset = 0;
  const active = hover != null ? segments[hover] : null;

  return (
    <Card>
      <CardHeader title={t("insights.donut.title", { n: data.top_n })} description={t("insights.donut.text")} />
      <div className="flex flex-col items-center gap-5 px-5 pb-5 sm:flex-row">
        <div className="relative shrink-0">
          <svg viewBox="0 0 180 180" className="size-[180px] -rotate-90">
            <circle cx={90} cy={90} r={R} fill="none" stroke="#f4f4f5" strokeWidth={STROKE} />
            {segments.map((s, i) => {
              const len = s.share * C;
              const el = (
                <circle key={i} cx={90} cy={90} r={R} fill="none" stroke={s.color} strokeWidth={hover === i ? STROKE + 6 : STROKE}
                  strokeDasharray={`${Math.max(0, len - 1.5)} ${C}`} strokeDashoffset={-offset}
                  className={cn("transition-[stroke-width] duration-150", s.id && "cursor-pointer")}
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => s.id && openNode(s.id)} />
              );
              offset += len;
              return el;
            })}
          </svg>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <p className="text-2xl font-semibold tabular-nums text-zinc-900">{pct(active ? active.share : data.kpis.top_intent_share)}</p>
            <p className="max-w-[96px] text-[11px] leading-tight text-zinc-500">{active ? active.label : t("insights.donut.center", { n: data.top_n })}</p>
          </div>
        </div>
        <ul className="w-full min-w-0 space-y-1">
          {segments.map((s, i) => (
            <li key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              className={cn("flex items-center gap-2 rounded-md px-2 py-1 text-[12.5px]", hover === i && "bg-zinc-50")}>
              <span className="size-2.5 shrink-0 rounded-sm border border-black/5" style={{ background: s.color }} />
              {s.id ? <button className="truncate text-left text-zinc-700 hover:text-blue-700 hover:underline cursor-pointer" onClick={() => openNode(s.id!)}>{s.label}</button>
                : <span className="truncate text-zinc-500">{s.label}</span>}
              <span className="ml-auto shrink-0 tabular-nums text-zinc-500">{s.intents}</span>
              <span className="w-10 shrink-0 text-right font-medium tabular-nums text-zinc-800">{pct(s.share)}</span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

export function CoverageCurve({ data }: { data: IntentVolume }) {
  const { t, pct } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const pts = data.coverage;
  const W = 520, H = 200, P = { l: 34, r: 12, t: 12, b: 24 };
  if (!pts.length) return null;
  const n = pts.length;
  const xs = (i: number) => P.l + (n === 1 ? 0 : (i / (n - 1)) * (W - P.l - P.r));
  const ys = (v: number) => H - P.b - v * (H - P.t - P.b);
  const d = pts.map((v, i) => `${i ? "L" : "M"}${xs(i)},${ys(v)}`).join("");
  const top = Math.min(data.top_n, n) - 1;
  const k80 = data.kpis.intents_for_80 != null ? data.kpis.intents_for_80 - 1 : null;
  const hp = hover != null ? hover : null;

  return (
    <Card>
      <CardHeader title={t("insights.coverage.title")} description={t("insights.coverage.text")} />
      <div className="relative px-4 pb-4">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }} preserveAspectRatio="none"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
            const x = ((e.clientX - r.left) / r.width) * W;
            setHover(Math.max(0, Math.min(n - 1, Math.round(((x - P.l) / (W - P.l - P.r)) * (n - 1)))));
          }}>
          {[0, 0.5, 1].map((v) => (
            <g key={v}>
              <line x1={P.l} x2={W - P.r} y1={ys(v)} y2={ys(v)} stroke="#f4f4f5" />
              <text x={P.l - 6} y={ys(v) + 3} textAnchor="end" className="fill-zinc-400 text-[9px]">{pct(v)}</text>
            </g>
          ))}
          {[1, Math.ceil(n / 2), n].map((v) => <text key={v} x={xs(v - 1)} y={H - 7} textAnchor="middle" className="fill-zinc-400 text-[9px]">{v}</text>)}
          <path d={`${d}L${xs(n - 1)},${ys(0)}L${xs(0)},${ys(0)}Z`} fill="rgb(37 99 235 / 0.07)" />
          <path d={d} fill="none" stroke="#2563eb" strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
          <line x1={xs(top)} x2={xs(top)} y1={ys(pts[top])} y2={ys(0)} stroke="#2563eb" strokeDasharray="2 3" />
          <circle cx={xs(top)} cy={ys(pts[top])} r={3.5} fill="#2563eb" />
          {k80 != null && <>
            <line x1={xs(k80)} x2={xs(k80)} y1={ys(pts[k80])} y2={ys(0)} stroke="#d97706" strokeDasharray="2 3" />
            <circle cx={xs(k80)} cy={ys(pts[k80])} r={3.5} fill="#d97706" />
          </>}
          {hp != null && <circle cx={xs(hp)} cy={ys(pts[hp])} r={3} fill="#18181b" />}
        </svg>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-500">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-blue-600" />{t("insights.coverage.top", { n: data.top_n, share: pct(pts[top]) })}</span>
          {k80 != null && <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-amber-600" />{t("insights.coverage.reach80", { n: k80 + 1 })}</span>}
          <span className="ml-auto">{t("insights.coverage.axis")}</span>
        </div>
        {hp != null && (
          <div className="pointer-events-none absolute right-6 top-0 rounded-md bg-zinc-900 px-2 py-1 text-[11px] text-white">
            {t("insights.coverage.hover", { n: hp + 1, share: pct(pts[hp]) })}{data.items[hp] ? ` · #${hp + 1} ${data.items[hp].label}` : ""}
          </div>
        )}
      </div>
    </Card>
  );
}
