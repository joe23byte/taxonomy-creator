import { useMemo, useState } from "react";
import type { Curve } from "@/lib/api";

export function DiscoveryCurve({ curve, height = 140 }: { curve: Curve | undefined; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = curve?.points ?? [];
  const W = 560, H = height, P = { l: 30, r: 10, t: 10, b: 22 };
  const { path, area, xs, ys, maxX, maxY } = useMemo(() => {
    const maxX = Math.max(10, pts.at(-1)?.interactions ?? 0);
    const maxY = Math.max(4, ...pts.map((p) => p.categories));
    const xs = (x: number) => P.l + (x / maxX) * (W - P.l - P.r);
    const ys = (y: number) => H - P.b - (y / maxY) * (H - P.t - P.b);
    let d = "";
    pts.forEach((p, i) => {
      const prev = pts[i - 1];
      d += i === 0 ? `M${xs(p.interactions)},${ys(p.categories)}` : `L${xs(p.interactions)},${ys(prev.categories)}L${xs(p.interactions)},${ys(p.categories)}`;
    });
    const area = pts.length ? `${d}L${xs(pts.at(-1)!.interactions)},${ys(0)}L${xs(pts[0].interactions)},${ys(0)}Z` : "";
    return { path: d, area, xs, ys, maxX, maxY };
  }, [pts, H]);

  if (!pts.length) {
    return <div className="flex items-center justify-center text-xs text-zinc-400" style={{ height }}>The curve appears once interactions are analysed.</div>;
  }
  const yTicks = [0, Math.round(maxY / 2), maxY];
  const xTicks = [0, Math.round(maxX / 2), maxX];
  const hp = hover != null ? pts[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} preserveAspectRatio="none"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const x = ((e.clientX - r.left) / r.width) * W;
          const n = ((x - P.l) / (W - P.l - P.r)) * maxX;
          let best = 0;
          pts.forEach((p, i) => { if (Math.abs(p.interactions - n) < Math.abs(pts[best].interactions - n)) best = i; });
          setHover(best);
        }}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={ys(t)} y2={ys(t)} stroke="#f4f4f5" />
            <text x={P.l - 6} y={ys(t) + 3} textAnchor="end" className="fill-zinc-400 text-[9px]">{t}</text>
          </g>
        ))}
        {xTicks.map((t) => <text key={t} x={xs(t)} y={H - 6} textAnchor="middle" className="fill-zinc-400 text-[9px]">{t}</text>)}
        {(curve?.batches ?? []).map((b, i) => (
          <line key={i} x1={xs(b.processed_total)} x2={xs(b.processed_total)} y1={P.t} y2={H - P.b} stroke="#ddd6fe" strokeDasharray="2 3" />
        ))}
        <path d={area} fill="rgb(37 99 235 / 0.07)" />
        <path d={path} fill="none" stroke="#2563eb" strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
        {hp && <circle cx={xs(hp.interactions)} cy={ys(hp.categories)} r={3} fill="#2563eb" />}
      </svg>
      {hp && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-md bg-zinc-900 px-2 py-1 text-[11px] text-white">
          {hp.interactions} interactions → {hp.categories} L4 categories
        </div>
      )}
    </div>
  );
}
