import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FolderOpen, FolderPlus, Pencil, Trash2 } from "lucide-react";
import { api, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge, Card, Input, Label, Spinner, Textarea } from "@/components/ui/primitives";

export function openProject(id: string) {
  return api.activateProject(id).then(() => {
    window.location.hash = "/workspace";
    window.location.reload();
  });
}

export function ProjectsView() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = useMutation({ mutationFn: openProject, onError: (e: Error) => setError(e.message) });
  const remove = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{t("projects.title")}</h1>
          <p className="mt-0.5 text-xs text-zinc-500">{t("projects.subtitle")}</p>
        </div>
        <Button onClick={() => setCreating(true)}><FolderPlus />{t("projects.new")}</Button>
      </div>
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      {!data ? <div className="flex h-40 items-center justify-center text-zinc-400"><Spinner /></div> : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.projects.map((p) => (
            <ProjectCard key={p.id} p={p} active={p.id === data.active} busy={open.isPending && open.variables === p.id}
              onOpen={() => { setError(null); open.mutate(p.id); }}
              onDelete={() => confirm(t("projects.confirmDelete", { name: p.name })) && remove.mutate(p.id)} />
          ))}
        </div>
      )}
      <CreateProjectDialog open={creating} onOpenChange={setCreating} />
    </div>
  );
}

function ProjectCard({ p, active, busy, onOpen, onDelete }: {
  p: Project; active: boolean; busy: boolean; onOpen: () => void; onDelete: () => void;
}) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(p.name);
  const [description, setDescription] = useState(p.description);
  const save = useMutation({
    mutationFn: () => api.updateProject(p.id, { name, description }),
    onSuccess: () => { setEditing(false); qc.invalidateQueries(); },
  });
  const s = p.stats ?? {};
  const stats: [string, React.ReactNode][] = [
    [t("projects.stats.interactions"), s.interactions ? `${s.processed ?? 0} / ${s.interactions}` : "0"],
    [t("projects.stats.taxonomy"), `${s.l1 ?? 0} L1 · ${s.l2 ?? 0} L2 · ${s.l4 ?? 0} L4`],
    [t("projects.stats.imports"), s.imports ?? 0],
    [t("projects.stats.proposals"), s.pending_proposals ?? 0],
  ];

  return (
    <Card className={cn("flex flex-col p-5", active && "border-blue-300 ring-1 ring-blue-200")}>
      {editing ? (
        <div className="space-y-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("projects.descriptionPlaceholder")} />
          {save.error && <p className="text-xs text-red-600">{(save.error as Error).message}</p>}
          <div className="flex gap-2">
            <Button size="sm" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>{t("common.save")}</Button>
            <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setName(p.name); setDescription(p.description); }}>{t("common.cancel")}</Button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-[15px] font-semibold leading-snug text-zinc-900">{p.name}</h3>
            {active && <Badge tone="blue"><CheckCircle2 />{t("projects.active")}</Badge>}
          </div>
          {p.description && <p className="mt-1 text-xs leading-relaxed text-zinc-500">{p.description}</p>}
          {s.dataset && <p className="mt-1 text-[11px] text-zinc-400">{t("projects.lastImport")}: {s.dataset}</p>}
        </>
      )}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {stats.map(([label, value]) => (
          <div key={label}>
            <dt className="text-zinc-400">{label}</dt>
            <dd className="font-medium tabular-nums text-zinc-800">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-[11px] text-zinc-400">
        {s.run_status ? `${t("projects.analysis")}: ${t(`runStatus.${s.run_status}`)} · ` : `${t("projects.noAnalysis")} · `}
        {s.last_activity ? formatDateTime(s.last_activity, lang) : formatDateTime(p.created_at, lang)}
      </p>
      <div className="mt-4 flex flex-1 items-end gap-1.5">
        {active ? (
          <Button size="sm" variant="secondary" onClick={() => { window.location.hash = "/workspace"; }}><FolderOpen />{t("projects.toWorkspace")}</Button>
        ) : (
          <Button size="sm" disabled={busy} onClick={onOpen}>{busy ? <Spinner /> : <FolderOpen />}{t("projects.open")}</Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setEditing(true)}><Pencil />{t("projects.rename")}</Button>
        {!active && <Button size="sm" variant="ghost" className="ml-auto text-red-600 hover:bg-red-50 hover:text-red-700" onClick={onDelete}><Trash2 />{t("common.delete")}</Button>}
      </div>
    </Card>
  );
}

export function CreateProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: async () => {
      const p = await api.createProject({ name, description });
      await openProject(p.id);
    },
  });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setName(""); setDescription(""); create.reset(); } }}>
      <DialogContent title={t("projects.createTitle")} description={t("projects.createDescription")}>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project-name">{t("projects.name")}</Label>
            <Input id="project-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={t("projects.namePlaceholder")}
              onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-description">{t("projects.description")}</Label>
            <Textarea id="project-description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("projects.descriptionPlaceholder")} />
          </div>
          <ol className="space-y-1 rounded-lg bg-zinc-50 px-4 py-3 text-xs text-zinc-600">
            <li><b className="font-medium text-zinc-800">1.</b> {t("projects.step1")}</li>
            <li><b className="font-medium text-zinc-800">2.</b> {t("projects.step2")}</li>
            <li><b className="font-medium text-zinc-800">3.</b> {t("projects.step3")}</li>
          </ol>
          {create.error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{(create.error as Error).message}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
            <Button disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
              {create.isPending && <Spinner />}{t("projects.createAndOpen")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
