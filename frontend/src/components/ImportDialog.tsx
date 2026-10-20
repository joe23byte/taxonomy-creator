import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, FileUp, Info, Sparkles, XCircle } from "lucide-react";
import { api, type ImportPreview } from "@/lib/api";
import { cn, titleCase } from "@/lib/utils";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { Badge, Input, Label, Select, Spinner } from "./ui/primitives";

const TARGETS: { key: string; label: string; hint?: string }[] = [
  { key: "conversation_id", label: "Conversation ID" },
  { key: "transcript", label: "Transcript text", hint: "Whole conversation in one cell (Customer: … / Agent: …)" },
  { key: "speaker", label: "Speaker", hint: "Turn-level files: one row per message" },
  { key: "text", label: "Message text", hint: "Turn-level files" },
  { key: "channel", label: "Channel" },
  { key: "segment", label: "Segment" },
  { key: "language", label: "Language" },
  { key: "timestamp", label: "Timestamp" },
  { key: "queue", label: "Queue" },
];

export function ImportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
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
  const commit = useMutation({
    mutationFn: () => api.commitImport(preview!.token, preview!.columns.length ? mapping : null, name || undefined),
    onSuccess: (r) => {
      qc.invalidateQueries();
      setDone(`Imported ${r.imported} interactions${r.skipped_existing ? ` · ${r.skipped_existing} already existed` : ""}.`);
      setPreview(null);
    },
    onError: (e: Error) => setError(e.message),
  });
  const sample = useMutation({
    mutationFn: api.loadSample,
    onSuccess: (r) => { qc.invalidateQueries(); setDone(`Loaded ${r.imported} sample interactions${r.skipped_existing ? ` · ${r.skipped_existing} already existed` : ""}.`); },
  });

  const pick = (list: FileList | null) => {
    if (!list?.length) return;
    const arr = Array.from(list);
    setFiles(arr);
    setName(arr.length === 1 ? arr[0].name : `${arr.length} files`);
    doPreview.mutate(arr);
  };
  const updateMapping = (k: string, v: string) => {
    const m = { ...mapping, [k]: v || null };
    setMapping(m);
    remap.mutate(m);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent wide title="Import interactions" description="JSON (canonical), CSV, Excel or plain-text transcripts. Data stays on this computer.">
        {done ? (
          <div className="flex flex-col items-center py-8 text-center">
            <CheckCircle2 className="size-8 text-emerald-500" />
            <p className="mt-3 text-sm font-medium text-zinc-800">{done}</p>
            <div className="mt-5 flex gap-2">
              <Button variant="secondary" onClick={reset}>Import more</Button>
              <Button onClick={() => { onOpenChange(false); reset(); }}>Done</Button>
            </div>
          </div>
        ) : !preview ? (
          <div className="space-y-4">
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
              onClick={() => input.current?.click()}
              className={cn("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition",
                drag ? "border-blue-400 bg-blue-50/50" : "border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50/50")}
            >
              {doPreview.isPending ? <Spinner className="text-blue-600" /> : <FileUp className="size-7 text-zinc-400" />}
              <p className="mt-3 text-sm font-medium text-zinc-800">Drop files here or click to browse</p>
              <p className="mt-1 text-xs text-zinc-500">.json · .csv · .xlsx · .txt (multiple TXT files = one interaction each)</p>
              <input ref={input} type="file" multiple className="hidden" accept=".json,.csv,.xlsx,.xls,.txt" onChange={(e) => pick(e.target.files)} />
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
              <label className="flex items-center gap-2">TXT separator (optional)
                <Input value={sep} onChange={(e) => setSep(e.target.value)} placeholder="e.g. ---" className="h-7 w-24 text-xs" />
              </label>
              <a href="/api/import/template.csv" className="ml-auto flex items-center gap-1 hover:text-zinc-800"><Download className="size-3.5" />CSV template</a>
              <a href="/api/import/sample.csv" className="flex items-center gap-1 hover:text-zinc-800"><Download className="size-3.5" />Sample CSV</a>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-zinc-100 bg-zinc-50/60 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-zinc-800">No data at hand?</p>
                <p className="text-xs text-zinc-500">100 synthetic telco conversations, generated with a fixed seed.</p>
              </div>
              <Button variant="secondary" onClick={() => sample.mutate()} disabled={sample.isPending}><Sparkles />Load 100 Sample Interactions</Button>
            </div>
            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="blue">{preview.format.toUpperCase()}</Badge>
              <span className="text-sm text-zinc-700"><b className="font-semibold">{preview.total}</b> valid interactions · avg. {preview.stats.avg_turns} turns</span>
              {preview.stats.channels.map((c) => <Badge key={c}>{titleCase(c)}</Badge>)}
              {preview.stats.segments.map((s) => <Badge key={s} tone="outline">{s}</Badge>)}
              <span className="ml-auto text-xs text-zinc-400">{files.map((f) => f.name).join(", ")}</span>
            </div>

            {preview.columns.length > 0 && (
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Column mapping</h4>
                <div className="grid grid-cols-3 gap-x-3 gap-y-2">
                  {TARGETS.map((t) => (
                    <div key={t.key} className="space-y-1">
                      <Label title={t.hint}>{t.label}</Label>
                      <Select value={mapping[t.key] ?? ""} onChange={(e) => updateMapping(t.key, e.target.value)} className="h-8 text-[13px]">
                        <option value="">— not mapped —</option>
                        {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                      </Select>
                    </div>
                  ))}
                </div>
                {remap.isPending && <p className="mt-2 text-xs text-zinc-400">Re-validating…</p>}
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
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Preview</h4>
                <div className="space-y-2">
                  {preview.preview.map((r) => (
                    <div key={r.conversation_id} className="rounded-lg border border-zinc-100 px-3 py-2">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-mono font-medium text-zinc-800">{r.conversation_id}</span>
                        {r.channel && <Badge>{titleCase(r.channel)}</Badge>}
                        {r.segment && <Badge tone="outline">{r.segment}</Badge>}
                        <span className="ml-auto text-zinc-400">{r.turn_count} turns</span>
                      </div>
                      <div className="mt-1 space-y-0.5">
                        {r.turns.slice(0, 3).map((t, i) => (
                          <p key={i} className="truncate text-xs text-zinc-600"><span className={cn("font-medium", t.speaker === "customer" ? "text-blue-700" : "text-zinc-500")}>{t.speaker}:</span> {t.text}</p>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-end gap-3 border-t border-zinc-100 pt-4">
              <div className="flex-1 space-y-1">
                <Label>Dataset name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <Button variant="ghost" onClick={reset}>Back</Button>
              <Button disabled={!preview.total || commit.isPending} onClick={() => commit.mutate()}>
                {commit.isPending && <Spinner />} Import {preview.total} interactions
              </Button>
            </div>
            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
