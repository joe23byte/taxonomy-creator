import { useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, RefreshCw, Sparkles } from "lucide-react";
import { api, type IntentVolume, type IntentVolumeItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardHeader, Spinner, Tip } from "@/components/ui/primitives";

export function TopIntents({ data, loadError, onRetry, analysisRunning, openNode }: {
  data: IntentVolume | undefined;
  loadError: boolean;
  onRetry: () => void;
  analysisRunning: boolean;
  openNode: (id: string) => void;
}) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const notes = useMutation({
    mutationFn: (force: boolean) => api.generateIntentNotes(force, lang),
    onSettled: () => qc.invalidateQueries({ queryKey: ["intent-volume"] }),
  });
  const top = data?.items.slice(0, data.top_n) ?? [];
  const missing = top.some((it) => !data?.notes[it.id] || data.notes[it.id].stale);
  const attempted = useRef<string | null>(null);
  const key = `${lang}|${data?.processed}|${top.map((it) => `${it.id}:${it.interactions}`).join(",")}`;

  useEffect(() => {
    if (!top.length || !missing || analysisRunning || notes.isPending || attempted.current === key) return;
    attempted.current = key;
    notes.mutate(false);
  }, [key, missing, analysisRunning, top.length, notes]);

  return (
    <Card>
      <CardHeader
        title={t("insights.top.title", { n: data?.top_n ?? 5 })}
        action={top.length > 0 && (
          <Tip content={t("insights.top.regenerateHint")}>
            <Button size="xs" variant="ghost" onClick={() => notes.mutate(true)} disabled={notes.isPending || analysisRunning}>
              {notes.isPending ? <Spinner className="size-3" /> : <RefreshCw />}{t("insights.top.regenerate")}
            </Button>
          </Tip>
        )}
      />
      <div className="px-5 pb-5">
        {loadError && !data ? (
          <p className="flex items-center gap-2 text-xs text-red-600">
            {t("insights.top.loadError")}
            <Button size="xs" variant="secondary" onClick={onRetry}><RefreshCw />{t("common.retry")}</Button>
          </p>
        ) : !data ? <p className="flex items-center gap-2 text-xs text-zinc-400"><Spinner className="size-3" />{t("common.loading")}</p>
        : !top.length ? <p className="text-xs text-zinc-400">{t("insights.top.empty")}</p> : (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {top.map((it) => (
                <IntentCard key={it.id} item={it} note={data!.notes[it.id]} generating={notes.isPending && (!data!.notes[it.id] || data!.notes[it.id].stale)}
                  waiting={analysisRunning} onOpen={() => openNode(it.id)} />
              ))}
            </div>
            <p className="mt-3 flex items-start gap-1.5 text-[11.5px] leading-relaxed text-zinc-500">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              <span>
                <b className="font-medium text-zinc-600">{t("insights.top.disclaimerLead")}</b> {t("insights.top.disclaimer")}
              </span>
            </p>
          </>
        )}
      </div>
    </Card>
  );
}

function IntentCard({ item, note, generating, waiting, onOpen }: {
  item: IntentVolumeItem;
  note: IntentVolume["notes"][string] | undefined;
  generating: boolean;
  waiting: boolean;
  onOpen: () => void;
}) {
  const { t, pct } = useI18n();
  const parents = item.path.slice(0, -1);
  return (
    <button onClick={onOpen}
      className="group flex flex-col rounded-xl border border-zinc-200/80 bg-white p-4 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition hover:border-blue-300 hover:shadow-sm cursor-pointer">
      <div className="flex items-start gap-2.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-[11px] font-semibold text-white">{item.rank}</span>
        <span className="flex min-w-0 flex-col gap-0.5 text-[11px] leading-snug text-zinc-500">
          {parents.map((p) => (
            <span key={p.id} className="flex gap-1.5">
              <span className="shrink-0 font-mono text-[10px] text-zinc-400">L{p.level}</span>{p.label}
            </span>
          ))}
        </span>
      </div>
      <p className="mt-2 flex min-h-[39px] gap-1.5 text-[14px] font-semibold leading-snug text-zinc-900 group-hover:text-blue-700">
        <span className="mt-[2px] shrink-0 self-start rounded bg-blue-50 px-1 font-mono text-[10px] font-medium leading-4 text-blue-600">L4</span>{item.label}
      </p>
      <div className="mt-3 flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-semibold tabular-nums tracking-tight text-zinc-900">{item.interactions}</p>
          <p className="text-[11px] text-zinc-500">{t("insights.top.interactions", { count: item.interactions })}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums text-blue-700">{pct(item.share)}</p>
          <p className="text-[11px] text-zinc-500">{t("insights.top.ofAll")}</p>
        </div>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
        <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, item.share * 100)}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1">
        {item.channels.slice(0, 2).map((c) => <Badge key={c.name}>{titleCase(c.name)} {pct(c.share)}</Badge>)}
        {item.segments[0] && <Badge tone="outline">{titleCase(item.segments[0].name)} {pct(item.segments[0].share)}</Badge>}
      </div>
      <div className="mt-3 flex flex-1 gap-1.5 border-t border-zinc-100 pt-3 text-[12px] leading-relaxed text-zinc-600">
        <Sparkles className="mt-0.5 size-3.5 shrink-0 text-violet-500" />
        {note && !note.stale ? <span>{note.text}</span>
          : generating ? <span className="text-zinc-400">{t("insights.top.writing")}</span>
          : note ? <span className="text-zinc-400">{note.text} <i>({t("insights.top.outdated")})</i></span>
          : <span className="text-zinc-400">{waiting ? t("insights.top.waiting") : t("insights.top.noNote")}</span>}
      </div>
    </button>
  );
}
