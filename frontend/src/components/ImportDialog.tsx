import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CheckCircle2, ChevronDown, ChevronRight, Copy, Download, FileUp, Info, Network, ShieldAlert, Sparkles, Table2, Upload, XCircle } from "lucide-react";
import { api, type ImportPreview } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, titleCase } from "@/lib/utils";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { Badge, Input, Label, Select, Spinner, Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/primitives";

const TARGETS: { key: string; hint?: boolean }[] = [
  { key: "conversation_id" },
  { key: "transcript", hint: true },
  { key: "speaker", hint: true },
  { key: "text", hint: true },
  { key: "channel" },
  { key: "segment" },
  { key: "language" },
  { key: "timestamp" },
  { key: "queue" },
];

const JSON_EXAMPLE = `[{
  "conversation_id": "CONV-0001",
  "channel": "voice", "segment": "prepaid",
  "language": "en", "timestamp": "2026-10-20T10:00:00Z",
  "turns": [
    {"speaker": "customer", "text": "My top-up is missing."},
    {"speaker": "agent", "text": "Let me check that."}
  ]
}]`;

const TAXONOMY_EXAMPLE = `{
  "name": "My taxonomy",
  "categories": [
    {"id": "L1-BIL", "level": 1, "parent_id": null,
     "label": "Billing & Payments",
     "description": "Invoices, charges and payments."},
    {"id": "L2-BIL-DSP", "level": 2, "parent_id": "L1-BIL",
     "label": "Billing Disputes",
     "description": "Customer believes a charge is wrong."}
  ]
}`;

export function ImportDialog({ open, onOpenChange, initialTab = "interactions" }: {
  open: boolean; onOpenChange: (o: boolean) => void; initialTab?: "interactions" | "taxonomy";
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [tab, setTab] = useState<string>(initialTab);
  const [next, setNext] = useState<string | null>(null);
  useEffect(() => { if (open) { setTab(initialTab); setNext(null); } }, [open, initialTab]);

  // Close once the project has both parts; otherwise lead to the missing one.
  const imported = async (kind: "interactions" | "taxonomy", message: string) => {
    await qc.invalidateQueries();
    const s = await qc.fetchQuery({ queryKey: ["summary"], queryFn: api.summary, staleTime: 0 });
    if (s.interactions > 0 && s.l2_nodes > 0) { onOpenChange(false); return; }
    const missing = kind === "taxonomy" ? "interactions" : "taxonomy";
    setNext(t(missing === "taxonomy" ? "import.nextTaxonomy" : "import.nextInteractions", { done: message }));
    setTab(missing);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide title={t("import.title")} description={t("import.description")}>
        {next && (
          <p className="mb-3 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800">
            <CheckCircle2 className="size-4 shrink-0" />{next}
          </p>
        )}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-4">
            <TabsTrigger value="interactions"><Table2 />{t("import.tabInteractions")}</TabsTrigger>
            <TabsTrigger value="taxonomy"><Network />{t("import.tabTaxonomy")}</TabsTrigger>
          </TabsList>
          <TabsContent value="interactions">
            <InteractionImport onClose={() => onOpenChange(false)} onImported={(m) => imported("interactions", m)} />
          </TabsContent>
          <TabsContent value="taxonomy"><TaxonomyImport onImported={(m) => imported("taxonomy", m)} /></TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function FormatHelp({ title, children, icon, defaultOpen = false }: {
  title: string; children: React.ReactNode; icon?: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => setOpen(defaultOpen), [defaultOpen]);
  return (
    <div className="rounded-xl border border-zinc-200">
      <button className="flex w-full items-center gap-1.5 px-4 py-2.5 text-left text-[13px] font-medium text-zinc-800 cursor-pointer" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown className="size-3.5 text-zinc-400" /> : <ChevronRight className="size-3.5 text-zinc-400" />}
        {icon ?? <Info className="size-3.5 text-blue-500" />}{title}
      </button>
      {open && <div className="space-y-3 border-t border-zinc-100 px-4 py-3 text-xs leading-relaxed text-zinc-600">{children}</div>}
    </div>
  );
}

function Code({ children }: { children: string }) {
  return <pre className="scroll-thin overflow-x-auto rounded-lg bg-zinc-900 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-zinc-100">{children}</pre>;
}

function InteractionImport({ onClose, onImported }: { onClose: () => void; onImported: (message: string) => void }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [name, setName] = useState("");
  const [sep, setSep] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const reset = () => { setPreview(null); setMapping({}); setName(""); setFiles([]); setError(null); setDone(null); };
  const doPreview = useMutation({
    mutationFn: (f: File[]) => api.previewImport(f, sep || undefined),
    onSuccess: (p) => { setPreview(p); setMapping(p.mapping); setError(null); },
    onError: (e: Error) => setError(e.message),
  });
  const remap = useMutation({
    mutationFn: (m: Record<string, string | null>) => api.remapImport(preview!.token, m),
    onSuccess: (p) => setPreview(p),
    onError: (e: Error) => setError(e.message),
  });
  const result = (r: { imported: number; skipped_existing: number }, key: string) =>
    t(key, { count: r.imported }) + (r.skipped_existing ? ` · ${t("import.skipped", { count: r.skipped_existing })}` : "");
  const commit = useMutation({
    mutationFn: () => api.commitImport(preview!.token, preview!.columns.length ? mapping : null, name || undefined),
    onSuccess: (r) => { const msg = result(r, "import.imported"); setDone(msg); setPreview(null); onImported(msg); },
    onError: (e: Error) => setError(e.message),
  });

  const pick = (list: FileList | null) => {
    if (!list?.length) return;
    const arr = Array.from(list);
    setFiles(arr);
    setName(arr.length === 1 ? arr[0].name : t("import.nFiles", { count: arr.length }));
    doPreview.mutate(arr);
  };
  const updateMapping = (k: string, v: string) => {
    const m = { ...mapping, [k]: v || null };
    setMapping(m);
    remap.mutate(m);
  };

  if (done) {
    return (
      <div className="flex flex-col items-center py-8 text-center">
        <CheckCircle2 className="size-8 text-emerald-500" />
        <p className="mt-3 text-sm font-medium text-zinc-800">{done}</p>
        <div className="mt-5 flex gap-2">
          <Button variant="secondary" onClick={reset}>{t("import.importMore")}</Button>
          <Button onClick={() => { onClose(); reset(); }}>{t("common.done")}</Button>
        </div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="space-y-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
          onClick={() => input.current?.click()}
          className={cn("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
            drag ? "border-blue-400 bg-blue-50/50" : "border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50/50")}
        >
          {doPreview.isPending ? <Spinner className="text-blue-600" /> : <FileUp className="size-7 text-zinc-400" />}
          <p className="mt-3 text-sm font-medium text-zinc-800">{t("import.drop")}</p>
          <p className="mt-1 text-xs text-zinc-500">{t("import.dropHint")}</p>
          <input ref={input} type="file" multiple className="hidden" accept=".json,.csv,.xlsx,.xls,.txt" onChange={(e) => pick(e.target.files)} />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
          <label className="flex items-center gap-2">{t("import.txtSeparator")}
            <Input value={sep} onChange={(e) => setSep(e.target.value)} placeholder={t("import.txtSeparatorPlaceholder")} className="h-7 w-24 text-xs" />
          </label>
          <a href="/api/import/template.json" className="ml-auto flex items-center gap-1 hover:text-zinc-800"><Download className="size-3.5" />{t("import.jsonTemplate")}</a>
          <a href="/api/import/template.csv" className="flex items-center gap-1 hover:text-zinc-800"><Download className="size-3.5" />{t("import.csvTemplate")}</a>
        </div>
        <FormatHelp title={t("import.formatTitle")}>
          <p>{t("import.formatIntro")}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <p className="font-semibold text-zinc-800">{t("import.formatJson")}</p>
              <Code>{JSON_EXAMPLE}</Code>
            </div>
            <ul className="list-disc space-y-1.5 pl-4">
              <li><b className="font-medium text-zinc-800">CSV / Excel:</b> {t("import.formatCsv")}</li>
              <li><b className="font-medium text-zinc-800">TXT:</b> {t("import.formatTxt")}</li>
              <li>{t("import.formatSpeakers")}</li>
              <li>{t("import.formatOptional")}</li>
              <li>{t("import.formatDuplicates")}</li>
            </ul>
          </div>
        </FormatHelp>
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="blue">{preview.format.toUpperCase()}</Badge>
        <span className="text-sm text-zinc-700">{t("import.validSummary", { count: preview.total, turns: preview.stats.avg_turns })}</span>
        {preview.stats.channels.map((c) => <Badge key={c}>{titleCase(c)}</Badge>)}
        {preview.stats.segments.map((s) => <Badge key={s} tone="outline">{s}</Badge>)}
        <span className="ml-auto text-xs text-zinc-400">{files.map((f) => f.name).join(", ")}</span>
      </div>

      {preview.columns.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">{t("import.columnMapping")}</h4>
          <div className="grid grid-cols-3 gap-x-3 gap-y-2">
            {TARGETS.map((f) => (
              <div key={f.key} className="space-y-1">
                <Label title={f.hint ? t(`import.fieldHints.${f.key}`) : undefined}>{t(`import.fields.${f.key}`)}</Label>
                <Select value={mapping[f.key] ?? ""} onChange={(e) => updateMapping(f.key, e.target.value)} className="h-8 text-[13px]">
                  <option value="">{t("import.notMapped")}</option>
                  {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </div>
            ))}
          </div>
          {remap.isPending && <p className="mt-2 text-xs text-zinc-400">{t("import.revalidating")}</p>}
        </div>
      )}

      {preview.issues.length > 0 && (
        <div className="scroll-thin max-h-32 space-y-1 overflow-y-auto rounded-lg border border-zinc-100 p-2.5">
          {preview.issues.map((i, k) => (
            <p key={k} className="flex items-start gap-1.5 text-xs text-zinc-600">
              {i.level === "error" ? <XCircle className="mt-px size-3 text-red-500" /> : i.level === "warning" ? <AlertTriangle className="mt-px size-3 text-amber-500" /> : <Info className="mt-px size-3 text-zinc-400" />}
              {i.record && <span className="font-mono text-zinc-400">{i.record}</span>} {i.message}
            </p>
          ))}
        </div>
      )}

      {preview.preview.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">{t("import.preview")}</h4>
          <div className="space-y-2">
            {preview.preview.map((r) => (
              <div key={r.conversation_id} className="rounded-lg border border-zinc-100 px-3 py-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono font-medium text-zinc-800">{r.conversation_id}</span>
                  {r.channel && <Badge>{titleCase(r.channel)}</Badge>}
                  {r.segment && <Badge tone="outline">{r.segment}</Badge>}
                  <span className="ml-auto text-zinc-400">{t("import.turns", { count: r.turn_count })}</span>
                </div>
                <div className="mt-1 space-y-0.5">
                  {r.turns.slice(0, 3).map((turn, i) => (
                    <p key={i} className="truncate text-xs text-zinc-600"><span className={cn("font-medium", turn.speaker === "customer" ? "text-blue-700" : "text-zinc-500")}>{t(`speaker.${turn.speaker}`)}:</span> {turn.text}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-end gap-3 border-t border-zinc-100 pt-4">
        <div className="flex-1 space-y-1">
          <Label>{t("import.datasetName")}</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button variant="ghost" onClick={reset}>{t("common.back")}</Button>
        <Button disabled={!preview.total || commit.isPending} onClick={() => commit.mutate()}>
          {commit.isPending && <Spinner />} {t("import.importN", { count: preview.total })}
        </Button>
      </div>
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
    </div>
  );
}

function TaxonomyImport({ onImported }: { onImported: (message: string) => void }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const [done, setDone] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: api.importTaxonomy,
    onSuccess: (r) => {
      const msg = t("taxImport.done", { lang: t(`languages.${r.language}`) });
      setDone(msg);
      onImported(msg);
    },
  });
  const s = summary.data;
  const empty = !!s && s.l2_nodes === 0;
  return (
    <div className="space-y-4">
      <p className="text-[13px] leading-relaxed text-zinc-600">{t("taxImport.intro")}</p>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-200 px-4 py-3">
        <p className="flex-1 text-xs text-zinc-500">
          {s && (empty ? t("taxImport.none") : t("taxImport.current", { l1: s.l1_nodes, l2: s.l2_nodes, lang: t(`languages.${s.taxonomy_language}`) }))}
        </p>
        <Button onClick={() => { setDone(null); input.current?.click(); }} disabled={upload.isPending}>
          {upload.isPending ? <Spinner /> : <Upload />}{t("taxImport.upload")}
        </Button>
        <input ref={input} type="file" accept=".json" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
      </div>
      {done && <p className="flex items-center gap-1.5 text-xs text-emerald-600"><CheckCircle2 className="size-3.5" />{done}</p>}
      {upload.error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{(upload.error as Error).message}</p>}

      <FormatHelp title={t("taxImport.promptTitle")} icon={<Sparkles className="size-3.5 text-violet-500" />} defaultOpen={empty}>
        <ol className="list-decimal space-y-1 pl-4">
          <li>{t("taxImport.promptStep1")}</li>
          <li>{t("taxImport.promptStep2")}</li>
          <li>{t("taxImport.promptStep3")}</li>
        </ol>
        <PromptBlock text={t("taxImport.prompt")} />
        <p className="flex items-start gap-1.5 text-amber-700"><ShieldAlert className="mt-px size-3.5 shrink-0" />{t("taxImport.promptPrivacy")}</p>
      </FormatHelp>

      <FormatHelp title={t("taxImport.formatTitle")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <p className="font-semibold text-zinc-800">{t("taxImport.example")}</p>
            <Code>{TAXONOMY_EXAMPLE}</Code>
          </div>
          <ul className="list-disc space-y-1.5 pl-4">
            <li>{t("taxImport.ruleLevels")}</li>
            <li>{t("taxImport.ruleIds")}</li>
            <li>{t("taxImport.ruleDescriptions")}</li>
            <li>{t("taxImport.ruleL3L4")}</li>
            <li>{t("taxImport.ruleWhen")}</li>
          </ul>
        </div>
      </FormatHelp>
    </div>
  );
}

function PromptBlock({ text }: { text: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative">
      <pre className="scroll-thin max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-900 px-3 py-2.5 pr-28 font-mono text-[11px] leading-relaxed text-zinc-100">{text}</pre>
      <Button size="xs" variant="secondary" className="absolute right-2 top-2" onClick={copy}>
        {copied ? <Check /> : <Copy />}{copied ? t("taxImport.copied") : t("taxImport.copy")}
      </Button>
    </div>
  );
}
