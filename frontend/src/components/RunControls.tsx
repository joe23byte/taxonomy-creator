import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, RotateCcw, Square, Workflow } from "lucide-react";
import { api, type Summary } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "./ui/button";
import { Progress, Spinner } from "./ui/primitives";
import { cn } from "@/lib/utils";

export function runPhase(s: Summary | undefined) {
  const status = s?.run?.status;
  const running = !!s?.worker_alive && (status === "running" || status === "stopping");
  const resumable = !running && (status === "paused" || status === "interrupted" || status === "stopped" || status === "failed") && (s?.pending ?? 0) > 0;
  return { status, running, resumable };
}

export function RunControls({ summary, size = "default" }: { summary: Summary | undefined; size?: "default" | "sm" }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { running, resumable, status } = runPhase(summary);
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSettled: () => qc.invalidateQueries({ queryKey: ["summary"] }),
  });
  const err = act.error as Error | null;
  const hasPending = (summary?.pending ?? 0) > 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {running ? (
        <>
          <Button size={size} variant="secondary" disabled={status === "stopping"} onClick={() => act.mutate(api.pause)}><Pause />{t("run.pause")}</Button>
          <Button size={size} variant="secondary" disabled={status === "stopping"} onClick={() => act.mutate(api.stop)}>
            {status === "stopping" ? <Spinner /> : <Square />}{t("run.stop")}
          </Button>
        </>
      ) : resumable ? (
        <Button size={size} onClick={() => act.mutate(api.resume)}><RotateCcw />{t("run.resume")}</Button>
      ) : (
        <Button size={size} disabled={!hasPending || !summary?.l2_nodes || act.isPending} onClick={() => act.mutate(api.start)}
          title={summary && !summary.l2_nodes ? t("run.needsTaxonomy") : undefined}><Play />{t("run.start")}</Button>
      )}
      {!running && (summary?.processed ?? 0) > 0 && (
        <Button size={size} variant="ghost" onClick={() => act.mutate(api.recluster)} title={t("run.reclusterHint")}>
          <Workflow />{t("run.recluster")}
        </Button>
      )}
      {!running && (summary?.failed ?? 0) > 0 && (
        <Button size={size} variant="ghost" onClick={() => act.mutate(api.retryFailed)}>{t("run.retryFailed", { count: summary!.failed })}</Button>
      )}
      {err && <span className="text-xs text-red-600">{err.message}</span>}
    </div>
  );
}

export function RunProgress({ summary, className }: { summary: Summary; className?: string }) {
  const { t } = useI18n();
  const { running } = runPhase(summary);
  const pct = summary.interactions ? Math.round((summary.processed / summary.interactions) * 100) : 0;
  const run = summary.run;
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          {running && <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-blue-400 opacity-60" /><span className="relative inline-flex size-2 rounded-full bg-blue-600" /></span>}
          <span className="truncate text-zinc-700">
            {running
              ? <>{run?.current_interaction ? <><span className="font-mono font-medium text-zinc-900">{run.current_interaction}</span> — </> : null}{run?.current_step ?? t("run.working")}</>
              : statusText(summary, t)}
          </span>
        </div>
        <span className="shrink-0 font-mono text-xs text-zinc-500 tabular-nums">{summary.processed}/{summary.interactions} · {pct}%</span>
      </div>
      <Progress value={pct} />
    </div>
  );
}

function statusText(s: Summary, t: (key: string, vars?: Record<string, string | number>) => string) {
  const st = s.run?.status;
  if (!s.interactions) return t("run.status.noData");
  if (!st) return t("run.status.ready", { count: s.pending });
  if (st === "completed") return s.pending ? t("run.status.completedWaiting", { count: s.pending }) : t("run.status.completed");
  if (st === "paused") return s.run?.error ? `${t("run.status.paused")} — ${s.run.error}` : t("run.status.paused");
  if (st === "interrupted") return t("run.status.interrupted");
  if (st === "stopped") return t("run.status.stopped");
  if (st === "failed") return `${t("run.status.failed")} — ${s.run?.error ?? t("run.status.seeActivity")}`;
  return st;
}
