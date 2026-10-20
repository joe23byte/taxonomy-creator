import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ShieldAlert, XCircle, Zap } from "lucide-react";
import { api, type ConnectionTest, type Settings } from "@/lib/api";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { Input, Label, Select, Spinner, Switch } from "./ui/primitives";

export function SettingsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: open });
  const status = useQuery({ queryKey: ["ollama-status"], queryFn: api.ollamaStatus, enabled: open });
  const [form, setForm] = useState<Partial<Settings>>({});
  const [test, setTest] = useState<ConnectionTest | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (data) setForm(data); }, [data]);

  const save = useMutation({
    mutationFn: () => api.saveSettings({
      ollama_url: form.ollama_url, llm_model: form.llm_model, embedding_model: form.embedding_model,
      batch_size: Number(form.batch_size), clustering_sensitivity: form.clustering_sensitivity,
      request_timeout: Number(form.request_timeout), auto_accept_new_categories: form.auto_accept_new_categories,
    }),
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      qc.invalidateQueries({ queryKey: ["ollama-status"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });
  const runTest = useMutation({
    mutationFn: () => api.testConnection({ ollama_url: form.ollama_url, llm_model: form.llm_model, embedding_model: form.embedding_model, request_timeout: Number(form.request_timeout) }),
    onSuccess: (r) => { setTest(r); qc.invalidateQueries({ queryKey: ["ollama-status"] }); },
  });
  const reset = useMutation({
    mutationFn: (which: "analysis" | "workspace") => (which === "analysis" ? api.resetAnalysis() : api.resetWorkspace()),
    onSuccess: () => qc.invalidateQueries(),
  });
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setForm((f) => ({ ...f, [k]: v }));
  const models = test?.models ?? status.data?.models ?? [];
  const preset = data?.sensitivity_presets?.[form.clustering_sensitivity ?? "medium"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Settings" description="Model server, analysis parameters and workspace maintenance.">
        {!data ? <Spinner /> : (
          <div className="space-y-6">
            <section className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="url">Ollama server URL</Label>
                <Input id="url" value={form.ollama_url ?? ""} onChange={(e) => set("ollama_url", e.target.value)} placeholder="http://192.168.1.20:11434" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Main LLM</Label>
                  <ModelPicker value={form.llm_model ?? ""} models={models.filter((m) => !m.includes("embed"))} onChange={(v) => set("llm_model", v)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Embedding model</Label>
                  <ModelPicker value={form.embedding_model ?? ""} models={models.filter((m) => m.includes("embed"))} onChange={(v) => set("embedding_model", v)} />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => runTest.mutate()} disabled={runTest.isPending}>
                  {runTest.isPending ? <Spinner /> : <Zap />} Test connection
                </Button>
                <span className="text-xs text-zinc-500">Runs a real inference and embedding request.</span>
              </div>
              {test && (
                <ul className="space-y-1 rounded-lg border border-zinc-100 bg-zinc-50/60 p-3 text-xs">
                  <TestRow ok={!!test.server?.ok} label="Server reachable" detail={test.server?.ok ? `${test.server.latency_ms} ms · ${test.models.length} models` : test.server?.error} />
                  {test.llm && <TestRow ok={test.llm.ok} label={`Inference · ${test.llm.model}`} detail={test.llm.ok ? `${test.llm.latency_ms} ms (structured JSON)` : test.llm.error} />}
                  {test.embedding && <TestRow ok={test.embedding.ok} label={`Embeddings · ${test.embedding.model}`} detail={test.embedding.ok ? `${test.embedding.dimensions} dimensions · ${test.embedding.latency_ms} ms` : test.embedding.error} />}
                </ul>
              )}
            </section>

            <section className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>Batch size</Label>
                <Input type="number" min={1} max={500} value={form.batch_size ?? 25} onChange={(e) => set("batch_size", Number(e.target.value))} />
              </div>
              <div className="space-y-1.5">
                <Label>Clustering sensitivity</Label>
                <Select value={form.clustering_sensitivity} onChange={(e) => set("clustering_sensitivity", e.target.value as Settings["clustering_sensitivity"])}>
                  <option value="low">Low — broader categories</option>
                  <option value="medium">Medium</option>
                  <option value="high">High — finer categories</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Request timeout (s)</Label>
                <Input type="number" min={5} max={1800} value={form.request_timeout ?? 180} onChange={(e) => set("request_timeout", Number(e.target.value))} />
              </div>
              {preset && (
                <p className="col-span-3 -mt-1 text-[11px] text-zinc-400">
                  Match existing category ≥ {preset.match.toFixed(2)} · cluster cohesion ≥ {preset.cluster.toFixed(2)} · overlap flagged ≥ {preset.merge.toFixed(2)} (cosine similarity)
                </p>
              )}
              <label className="col-span-3 flex items-center justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-2.5">
                <span>
                  <span className="block text-sm text-zinc-800">Auto-accept new categories</span>
                  <span className="block text-xs text-zinc-500">Only clearly non-conflicting new L3/L4 nodes. Merges and splits always require review.</span>
                </span>
                <Switch checked={!!form.auto_accept_new_categories} onCheckedChange={(v) => set("auto_accept_new_categories", v)} />
              </label>
            </section>

            <div className="flex items-start gap-2 rounded-lg bg-amber-50/70 px-3 py-2.5 text-xs text-amber-800">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" />
              <p>Transcript text is sent to the Ollama server for inference. If it runs on another machine, use only synthetic data or an approved, secured network connection for real customer data. No other external service receives data.</p>
            </div>

            <div className="flex items-center justify-end gap-2">
              {saved && <span className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle2 className="size-3.5" />Saved</span>}
              <Button onClick={() => save.mutate()} disabled={save.isPending}>Save settings</Button>
            </div>

            <section className="border-t border-zinc-100 pt-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Workspace</h4>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="danger" size="sm" onClick={() => confirm("Remove all analysis results (intents, L3/L4 categories, proposals, reviews)? Imported interactions are kept.") && reset.mutate("analysis")}>Reset analysis</Button>
                <Button variant="danger" size="sm" onClick={() => confirm("Delete all imported interactions and analysis results?") && reset.mutate("workspace")}>Clear workspace</Button>
              </div>
              {reset.error && <p className="mt-2 text-xs text-red-600">{(reset.error as Error).message}</p>}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ModelPicker({ value, models, onChange }: { value: string; models: string[]; onChange: (v: string) => void }) {
  if (!models.length || !models.includes(value) && value) {
    return <Input value={value} onChange={(e) => onChange(e.target.value)} list="models-list" />;
  }
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      {models.map((m) => <option key={m} value={m}>{m}</option>)}
    </Select>
  );
}

function TestRow({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? <CheckCircle2 className="mt-px size-3.5 text-emerald-600" /> : <XCircle className="mt-px size-3.5 text-red-500" />}
      <span className="font-medium text-zinc-700">{label}</span>
      <span className="ml-auto text-right text-zinc-500">{detail}</span>
    </li>
  );
}
