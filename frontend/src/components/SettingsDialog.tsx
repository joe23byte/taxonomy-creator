import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ImageUp, ShieldAlert, Trash2, XCircle, Zap } from "lucide-react";
import { api, type Branding, type ConnectionTest, type Settings } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { Input, Label, Select, Spinner, Switch } from "./ui/primitives";

export function SettingsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
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
      taxonomy_language: form.taxonomy_language,
    }),
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      qc.invalidateQueries({ queryKey: ["ollama-status"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
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
      <DialogContent title={t("settings.title")} description={t("settings.description")}>
        {!data ? <Spinner /> : (
          <div className="space-y-6">
            <section className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="url">{t("settings.ollamaUrl")}</Label>
                <Input id="url" value={form.ollama_url ?? ""} onChange={(e) => set("ollama_url", e.target.value)} placeholder="http://192.168.1.20:11434" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>{t("settings.llm")}</Label>
                  <ModelPicker value={form.llm_model ?? ""} models={models.filter((m) => !m.includes("embed"))} onChange={(v) => set("llm_model", v)} />
                </div>
                <div className="space-y-1.5">
                  <Label>{t("settings.embedding")}</Label>
                  <ModelPicker value={form.embedding_model ?? ""} models={models.filter((m) => m.includes("embed"))} onChange={(v) => set("embedding_model", v)} />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => runTest.mutate()} disabled={runTest.isPending}>
                  {runTest.isPending ? <Spinner /> : <Zap />} {t("settings.test")}
                </Button>
                <span className="text-xs text-zinc-500">{t("settings.testHint")}</span>
              </div>
              {test && (
                <ul className="space-y-1 rounded-lg border border-zinc-100 bg-zinc-50/60 p-3 text-xs">
                  <TestRow ok={!!test.server?.ok} label={t("settings.serverReachable")} detail={test.server?.ok ? t("settings.serverDetail", { ms: test.server.latency_ms, count: test.models.length }) : test.server?.error} />
                  {test.llm && <TestRow ok={test.llm.ok} label={`${t("settings.inference")} · ${test.llm.model}`} detail={test.llm.ok ? t("settings.inferenceDetail", { ms: test.llm.latency_ms }) : test.llm.error} />}
                  {test.embedding && <TestRow ok={test.embedding.ok} label={`${t("settings.embeddings")} · ${test.embedding.model}`} detail={test.embedding.ok ? t("settings.embeddingDetail", { dims: test.embedding.dimensions, ms: test.embedding.latency_ms }) : test.embedding.error} />}
                </ul>
              )}
            </section>

            <section className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>{t("settings.batchSize")}</Label>
                <Input type="number" min={1} max={500} value={form.batch_size ?? 25} onChange={(e) => set("batch_size", Number(e.target.value))} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("settings.sensitivity")}</Label>
                <Select value={form.clustering_sensitivity} onChange={(e) => set("clustering_sensitivity", e.target.value as Settings["clustering_sensitivity"])}>
                  <option value="low">{t("settings.sensLow")}</option>
                  <option value="medium">{t("settings.sensMedium")}</option>
                  <option value="high">{t("settings.sensHigh")}</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("settings.timeout")}</Label>
                <Input type="number" min={5} max={1800} value={form.request_timeout ?? 180} onChange={(e) => set("request_timeout", Number(e.target.value))} />
              </div>
              {preset && (
                <p className="col-span-3 -mt-1 text-[11px] text-zinc-400">
                  {t("settings.thresholds", { match: preset.match.toFixed(2), cluster: preset.cluster.toFixed(2), merge: preset.merge.toFixed(2) })}
                </p>
              )}
              <div className="col-span-3 space-y-1.5">
                <Label>{t("settings.language")}</Label>
                <Select value={form.taxonomy_language ?? "en"} onChange={(e) => set("taxonomy_language", e.target.value)} className="w-56">
                  {Object.keys(data.languages ?? {}).map((code) => <option key={code} value={code}>{t(`languages.${code}`)}</option>)}
                </Select>
                <p className="text-[11px] text-zinc-400">{t("settings.languageHint")}</p>
              </div>
              <label className="col-span-3 flex items-center justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-2.5">
                <span>
                  <span className="block text-sm text-zinc-800">{t("settings.autoAccept")}</span>
                  <span className="block text-xs text-zinc-500">{t("settings.autoAcceptHint")}</span>
                </span>
                <Switch checked={!!form.auto_accept_new_categories} onCheckedChange={(v) => set("auto_accept_new_categories", v)} />
              </label>
            </section>

            <div className="flex items-start gap-2 rounded-lg bg-amber-50/70 px-3 py-2.5 text-xs text-amber-800">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" />
              <p>{t("settings.privacy")}</p>
            </div>

            <div className="flex items-center justify-end gap-2">
              {saved && <span className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle2 className="size-3.5" />{t("settings.saved")}</span>}
              <Button onClick={() => save.mutate()} disabled={save.isPending}>{t("settings.save")}</Button>
            </div>

            <BrandingSection />

            <section className="border-t border-zinc-100 pt-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">{t("settings.maintenance")}</h4>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="danger" size="sm" onClick={() => confirm(t("settings.confirmResetAnalysis")) && reset.mutate("analysis")}>{t("settings.resetAnalysis")}</Button>
                <Button variant="danger" size="sm" onClick={() => confirm(t("settings.confirmClear")) && reset.mutate("workspace")}>{t("settings.clear")}</Button>
              </div>
              {reset.error && <p className="mt-2 text-xs text-red-600">{(reset.error as Error).message}</p>}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function BrandingSection() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const { data } = useQuery({ queryKey: ["branding"], queryFn: api.branding });
  const onDone = (b: Branding) => qc.setQueryData(["branding"], b);
  const upload = useMutation({ mutationFn: api.uploadLogo, onSuccess: onDone });
  const remove = useMutation({ mutationFn: api.deleteLogo, onSuccess: onDone });
  const error = (upload.error ?? remove.error) as Error | null;
  return (
    <section className="border-t border-zinc-100 pt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">{t("settings.branding")}</h4>
      <div className="mt-2 flex items-center gap-3">
        <div className="flex h-12 w-40 shrink-0 items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-zinc-50/60 px-2">
          {data?.logo
            ? <img src={`/api/branding/logo?v=${data.version}`} alt="" className="max-h-9 max-w-full object-contain" />
            : <span className="text-[11px] text-zinc-400">{t("settings.noLogo")}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => input.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? <Spinner /> : <ImageUp />}{data?.logo ? t("settings.replaceLogo") : t("settings.uploadLogo")}
          </Button>
          {data?.logo && <Button size="sm" variant="ghost" onClick={() => remove.mutate()}><Trash2 />{t("settings.removeLogo")}</Button>}
        </div>
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
      </div>
      <p className="mt-1.5 text-[11px] text-zinc-400">{t("settings.brandingHint")}</p>
      {error && <p className="mt-1 text-xs text-red-600">{error.message}</p>}
    </section>
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
