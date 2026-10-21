import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileJson, FileSpreadsheet, FileText, Presentation } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Dialog, DialogContent } from "./ui/dialog";
import { Select, Spinner } from "./ui/primitives";
import { cn } from "@/lib/utils";

const SHEETS = [
  { id: "Taxonomy", key: "taxonomy" },
  { id: "Interaction Assignments", key: "assignments" },
  { id: "Review Queue", key: "review" },
  { id: "Taxonomy Changes", key: "changes" },
];

export function ExportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t, lang } = useI18n();
  const [sheet, setSheet] = useState("");
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary, enabled: open });
  const csvHref = `/api/export/csv?lang=${lang}` + (sheet ? `&sheet=${encodeURIComponent(sheet)}` : "");
  const report = useMutation({
    mutationFn: async () => {
      // Notes are optional in the report; a missing model must not block the download.
      await api.generateIntentNotes(false, lang).catch(() => undefined);
      return api.reportPdf(lang);
    },
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: `intent_studio_report_${new Date().toISOString().slice(0, 10)}.pdf` });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  const analysisLang = summary.data ? t(`languages.${summary.data.taxonomy_language}`) : "—";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={t("export.title")} description={t("export.description")}>
        <div className="space-y-2">
          <button onClick={() => report.mutate()} disabled={report.isPending}
            className="flex w-full items-start gap-3 rounded-xl border border-zinc-200 p-4 text-left transition hover:bg-zinc-50 cursor-pointer disabled:cursor-wait">
            <Icon>{report.isPending ? <Spinner /> : <Presentation />}</Icon>
            <div>
              <p className="text-sm font-medium text-zinc-900">{t("export.report")}</p>
              <p className="text-xs text-zinc-500">{report.isPending ? t("export.reportBusy") : t("export.reportText")}</p>
              {report.error && <p className="mt-1 text-xs text-red-600">{t("export.reportError", { error: (report.error as Error).message })}</p>}
            </div>
          </button>
          <Option href={`/api/export/xlsx?lang=${lang}`} icon={<FileSpreadsheet />} title={t("export.excel")} recommended text={t("export.excelText")} />
          <div className="rounded-xl border border-zinc-200 p-4">
            <div className="flex items-start gap-3">
              <Icon><FileText /></Icon>
              <div className="flex-1">
                <p className="text-sm font-medium text-zinc-900">CSV</p>
                <p className="text-xs text-zinc-500">{t("export.csvText")}</p>
                <div className="mt-2 flex gap-2">
                  <Select value={sheet} onChange={(e) => setSheet(e.target.value)} className="h-8 text-[13px]">
                    <option value="">{t("export.allSheets")}</option>
                    {SHEETS.map((s) => <option key={s.id} value={s.id}>{t(`export.sheets.${s.key}`)}</option>)}
                  </Select>
                  <a href={csvHref} className="inline-flex h-8 items-center rounded-lg bg-zinc-900 px-3 text-[13px] font-medium text-white hover:bg-zinc-800">{t("export.download")}</a>
                </div>
              </div>
            </div>
          </div>
          <Option href="/api/export/json" icon={<FileJson />} title="JSON" text={t("export.jsonText")} />
          <p className="pt-1 text-[11px] text-zinc-400">{t("export.languageNote", { lang: analysisLang })}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Icon({ children }: { children: React.ReactNode }) {
  return <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600 [&_svg]:size-4">{children}</div>;
}

function Option({ href, icon, title, text, recommended }: { href: string; icon: React.ReactNode; title: string; text: string; recommended?: boolean }) {
  const { t } = useI18n();
  return (
    <a href={href} className={cn("flex items-start gap-3 rounded-xl border p-4 transition hover:bg-zinc-50", recommended ? "border-blue-200 bg-blue-50/30" : "border-zinc-200")}>
      <Icon>{icon}</Icon>
      <div>
        <p className="text-sm font-medium text-zinc-900">{title} {recommended && <span className="ml-1 text-xs font-normal text-blue-600">{t("export.recommended")}</span>}</p>
        <p className="text-xs text-zinc-500">{text}</p>
      </div>
    </a>
  );
}
