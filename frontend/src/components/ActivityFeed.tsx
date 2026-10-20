import { useMemo, useState } from "react";
import {
  AlertTriangle, Boxes, CheckCircle2, CircleDot, GitBranchPlus, GitMerge, Layers, Link2, ListChecks, Orbit, Pause,
  PenLine, Play, ScanText, Sparkles, Split, Square, UserCheck, Waypoints, XCircle, Info, CircleCheckBig, Radio,
} from "lucide-react";
import type { AnalysisEvent } from "@/lib/api";
import { useLive } from "@/lib/live";
import { cn, formatTime } from "@/lib/utils";
import { Badge, Empty, type Tone } from "./ui/primitives";

type Meta = { icon: typeof Info; tone: Tone; label: string; group: "interaction" | "taxonomy" | "run" | "review" };

export const EVENT_META: Record<string, Meta> = {
  extracting: { icon: ScanText, tone: "neutral", label: "Extracting", group: "interaction" },
  intents_extracted: { icon: ListChecks, tone: "neutral", label: "Intents identified", group: "interaction" },
  embedding: { icon: Waypoints, tone: "neutral", label: "Embedding", group: "interaction" },
  candidate_extracted: { icon: CircleDot, tone: "outline", label: "Extracted candidate", group: "interaction" },
  matched_existing: { icon: Link2, tone: "green", label: "Matched existing intent", group: "interaction" },
  candidate_new: { icon: Sparkles, tone: "blue", label: "New intent candidate", group: "interaction" },
  cluster_forming: { icon: Orbit, tone: "violet", label: "Cluster forming", group: "interaction" },
  interaction_assigned: { icon: CircleCheckBig, tone: "neutral", label: "Interaction assigned", group: "interaction" },
  needs_review: { icon: AlertTriangle, tone: "amber", label: "Needs human review", group: "review" },
  no_intent: { icon: AlertTriangle, tone: "amber", label: "Needs human review", group: "review" },
  interaction_failed: { icon: XCircle, tone: "red", label: "Failed", group: "review" },
  batch_refinement: { icon: Layers, tone: "violet", label: "Refining taxonomy", group: "taxonomy" },
  cluster_discovered: { icon: Boxes, tone: "violet", label: "New cluster discovered", group: "taxonomy" },
  outlier_pass: { icon: Orbit, tone: "violet", label: "Rare intents", group: "taxonomy" },
  category_proposed: { icon: GitBranchPlus, tone: "blue", label: "Category proposed", group: "taxonomy" },
  category_approved: { icon: CheckCircle2, tone: "green", label: "Category approved", group: "taxonomy" },
  category_refined: { icon: PenLine, tone: "blue", label: "Category refined", group: "taxonomy" },
  merge_proposed: { icon: GitMerge, tone: "amber", label: "Merge proposed", group: "taxonomy" },
  split_proposed: { icon: Split, tone: "amber", label: "Split proposed", group: "taxonomy" },
  proposal_accepted: { icon: CheckCircle2, tone: "green", label: "Change approved", group: "taxonomy" },
  proposal_rejected: { icon: XCircle, tone: "neutral", label: "Change rejected", group: "taxonomy" },
  taxonomy_edited: { icon: PenLine, tone: "neutral", label: "Edited", group: "taxonomy" },
  assignment_corrected: { icon: UserCheck, tone: "green", label: "Reviewer", group: "review" },
  run_started: { icon: Play, tone: "blue", label: "Run", group: "run" },
  run_resumed: { icon: Play, tone: "blue", label: "Run", group: "run" },
  run_paused: { icon: Pause, tone: "amber", label: "Run", group: "run" },
  run_stopped: { icon: Square, tone: "neutral", label: "Run", group: "run" },
  run_completed: { icon: CheckCircle2, tone: "green", label: "Run", group: "run" },
  run_failed: { icon: XCircle, tone: "red", label: "Run", group: "run" },
  warning: { icon: AlertTriangle, tone: "amber", label: "Warning", group: "review" },
  error: { icon: XCircle, tone: "red", label: "Error", group: "review" },
  info: { icon: Info, tone: "neutral", label: "Info", group: "run" },
};

const FILTERS = [
  { id: "all", label: "All" },
  { id: "taxonomy", label: "Taxonomy" },
  { id: "interaction", label: "Interactions" },
  { id: "review", label: "Warnings & review" },
] as const;

const QUIET = new Set(["extracting", "embedding", "candidate_extracted"]);

export function ActivityFeed({ className, compact = false, onOpenConversation, onOpenNode }: {
  className?: string;
  compact?: boolean;
  onOpenConversation?: (conversationId: string) => void;
  onOpenNode?: (nodeId: string) => void;
}) {
  const { events, connected } = useLive();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [verbose, setVerbose] = useState(false);
  const shown = useMemo(() => events.filter((e) => {
    const meta = EVENT_META[e.kind] ?? EVENT_META.info;
    if (!verbose && QUIET.has(e.kind) && filter === "all") return false;
    if (filter === "all") return true;
    if (filter === "review") return meta.group === "review" || e.level === "warning" || e.level === "error";
    return meta.group === filter;
  }).slice(0, compact ? 60 : 250), [events, filter, verbose, compact]);

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-1.5 px-4 pb-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={cn("rounded-md px-2 py-1 text-xs font-medium transition cursor-pointer",
              filter === f.id ? "bg-zinc-900 text-white" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800")}
          >
            {f.label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-zinc-500 cursor-pointer select-none">
          <input type="checkbox" className="accent-blue-600" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          All steps
        </label>
        <span className={cn("flex items-center gap-1 text-[11px]", connected ? "text-emerald-600" : "text-zinc-400")}>
          <Radio className="size-3" /> {connected ? "Live" : "Reconnecting"}
        </span>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {shown.length === 0 ? (
          <Empty icon={<Radio />} title="No activity yet" description="Processing events appear here in real time once an analysis runs." />
        ) : (
          <ol className="space-y-px">
            {shown.map((e) => <EventRow key={e.id} e={e} onOpenConversation={onOpenConversation} onOpenNode={onOpenNode} />)}
          </ol>
        )}
      </div>
    </div>
  );
}

function EventRow({ e, onOpenConversation, onOpenNode }: {
  e: AnalysisEvent; onOpenConversation?: (id: string) => void; onOpenNode?: (id: string) => void;
}) {
  const meta = EVENT_META[e.kind] ?? EVENT_META.info;
  const Icon = meta.icon;
  const iconTone = {
    neutral: "text-zinc-400", outline: "text-zinc-400", blue: "text-blue-600", green: "text-emerald-600",
    amber: "text-amber-500", red: "text-red-500", violet: "text-violet-500", dashed: "text-blue-600",
  }[meta.tone];
  const showBadge = !["neutral", "outline"].includes(meta.tone) || e.kind === "candidate_extracted" || e.kind === "interaction_assigned";
  const clickable = (e.node_id && onOpenNode && e.level !== "error") || (e.conversation_id && onOpenConversation);
  return (
    <li
      className={cn("group flex items-start gap-2.5 rounded-lg px-2 py-1.5 animate-fade-in", clickable && "cursor-pointer hover:bg-zinc-50")}
      onClick={() => {
        if (e.node_id && onOpenNode && !e.conversation_id) onOpenNode(e.node_id);
        else if (e.conversation_id && onOpenConversation) onOpenConversation(e.conversation_id);
      }}
    >
      <Icon className={cn("mt-0.5 size-3.5 shrink-0", iconTone)} />
      <div className="min-w-0 flex-1">
        <p className={cn("text-[13px] leading-5 text-zinc-700", e.level === "error" && "text-red-700", meta.group === "taxonomy" && "font-medium text-zinc-900")}>
          {e.message}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2 pt-0.5">
        {showBadge && <Badge tone={meta.tone}>{meta.label}</Badge>}
        <span className="w-14 text-right font-mono text-[10px] text-zinc-400 tabular-nums">{formatTime(e.created_at)}</span>
      </div>
    </li>
  );
}
