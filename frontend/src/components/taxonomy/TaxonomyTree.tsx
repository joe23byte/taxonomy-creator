import { memo, useEffect, useMemo, useState } from "react";
import { ChevronRight, GitMerge, Lock, Search, Sparkles, Split, UserPen, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import type { TaxNode } from "@/lib/api";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import { Badge, Input, Tip } from "../ui/primitives";

export function buildChildren(nodes: TaxNode[]) {
  const map = new Map<string | null, TaxNode[]>();
  for (const n of nodes) {
    const arr = map.get(n.parent_id) ?? [];
    arr.push(n);
    map.set(n.parent_id, arr);
  }
  for (const arr of map.values()) {
    arr.sort((a, b) => (a.level <= 2 ? a.label.localeCompare(b.label) : b.interaction_count - a.interaction_count || a.label.localeCompare(b.label)));
  }
  return map;
}

export function TaxonomyTree({ nodes, selectedId, onSelect, autoExpand = true }: {
  nodes: TaxNode[]; selectedId: string | null; onSelect: (id: string) => void; autoExpand?: boolean;
}) {
  const { highlights } = useLive();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(nodes.filter((n) => n.level === 1).map((n) => n.id)));
  const children = useMemo(() => buildChildren(nodes), [nodes]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  // auto-expand ancestors of categories that were just touched by the analysis
  useEffect(() => {
    if (!autoExpand) return;
    const ids = Object.keys(highlights);
    if (!ids.length) return;
    setExpanded((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const id of ids) {
        let cur = byId.get(id);
        while (cur?.parent_id) {
          if (!next.has(cur.parent_id)) { next.add(cur.parent_id); changed = true; }
          cur = byId.get(cur.parent_id);
        }
      }
      return changed ? next : prev;
    });
  }, [highlights, byId, autoExpand]);

  // ensure L1s are expanded once they arrive
  useEffect(() => {
    setExpanded((prev) => {
      const l1 = nodes.filter((n) => n.level === 1 && !prev.has(n.id));
      if (!l1.length || prev.size > 0) return prev;
      return new Set([...prev, ...l1.map((n) => n.id)]);
    });
  }, [nodes]);

  const visible = useMemo(() => {
    if (!query.trim()) return null;
    const q = query.toLowerCase();
    const keep = new Set<string>();
    for (const n of nodes) {
      if (n.label.toLowerCase().includes(q) || n.description.toLowerCase().includes(q) || n.id.toLowerCase() === q) {
        let cur: TaxNode | undefined = n;
        while (cur) { keep.add(cur.id); cur = cur.parent_id ? byId.get(cur.parent_id) : undefined; }
      }
    }
    return keep;
  }, [query, nodes, byId]);

  const toggle = (id: string) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });
  const roots = (children.get(null) ?? []).filter((n) => !visible || visible.has(n.id));
  const allExpanded = nodes.filter((n) => children.has(n.id)).every((n) => expanded.has(n.id));

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center gap-2 px-4 pb-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search categories…" className="h-8 pl-8 text-[13px]" />
        </div>
        <Tip content={allExpanded ? "Collapse all" : "Expand all"}>
          <button
            aria-label={allExpanded ? "Collapse all" : "Expand all"}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 cursor-pointer"
            onClick={() => setExpanded(allExpanded ? new Set() : new Set(nodes.filter((n) => children.has(n.id)).map((n) => n.id)))}
          >
            {allExpanded ? <ChevronsDownUp className="size-4" /> : <ChevronsUpDown className="size-4" />}
          </button>
        </Tip>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-4" role="tree">
        {roots.map((n) => (
          <Branch key={n.id} node={n} children={children} expanded={expanded} visible={visible} toggle={toggle}
            selectedId={selectedId} onSelect={onSelect} highlights={highlights} />
        ))}
      </div>
    </div>
  );
}

interface BranchProps {
  node: TaxNode;
  children: Map<string | null, TaxNode[]>;
  expanded: Set<string>;
  visible: Set<string> | null;
  toggle: (id: string) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  highlights: Record<string, { kind: string; at: number }>;
}

function Branch(props: BranchProps) {
  const { node, children, expanded, visible } = props;
  const kids = (children.get(node.id) ?? []).filter((k) => !visible || visible.has(k.id));
  const isOpen = visible ? true : expanded.has(node.id);
  return (
    <div role="treeitem" aria-expanded={kids.length ? isOpen : undefined}>
      <NodeRow node={node} hasKids={kids.length > 0} isOpen={isOpen} toggle={props.toggle}
        selected={props.selectedId === node.id} onSelect={props.onSelect} highlight={props.highlights[node.id]?.kind} />
      {isOpen && kids.length > 0 && (
        <div className={cn("relative ml-[15px] border-l pl-2", node.level >= 2 ? "border-blue-100" : "border-zinc-100")}>
          {kids.map((k) => <Branch key={k.id} {...props} node={k} />)}
        </div>
      )}
    </div>
  );
}

const NodeRow = memo(function NodeRow({ node, hasKids, isOpen, toggle, selected, onSelect, highlight }: {
  node: TaxNode; hasKids: boolean; isOpen: boolean; toggle: (id: string) => void; selected: boolean;
  onSelect: (id: string) => void; highlight?: string;
}) {
  const fixed = node.level <= 2;
  const proposed = node.status === "proposed";
  const inactive = ["merged", "split", "retired"].includes(node.status);
  const merge = node.flags.some((f) => f.type === "merge");
  const split = node.flags.some((f) => f.type === "split");
  // animate only rows whose category was created moments ago (stable keys keep existing rows untouched)
  const [isNew] = useState(() => node.level >= 3 && Date.now() - new Date(node.created_at).getTime() < 15000);
  const hl = highlight
    ? highlight === "merge_proposed" || highlight === "split_proposed"
      ? "bg-amber-50 ring-1 ring-amber-200"
      : highlight === "category_refined"
        ? "bg-violet-50 ring-1 ring-violet-200"
        : "bg-blue-50 ring-1 ring-blue-200"
    : "";

  return (
    <div
      className={cn(
        "group flex h-8 items-center gap-1.5 rounded-md pr-2 transition-[background-color,box-shadow] duration-500 cursor-pointer",
        selected ? "bg-zinc-100" : "hover:bg-zinc-50",
        hl,
        isNew && "animate-node-in",
        inactive && "opacity-50",
      )}
      onClick={() => onSelect(node.id)}
    >
      <button
        className={cn("flex size-5 shrink-0 items-center justify-center rounded text-zinc-400 hover:text-zinc-700 cursor-pointer", !hasKids && "invisible")}
        onClick={(e) => { e.stopPropagation(); toggle(node.id); }}
        aria-label={isOpen ? "Collapse" : "Expand"}
      >
        <ChevronRight className={cn("size-3.5 transition-transform duration-200", isOpen && "rotate-90")} />
      </button>
      <span className={cn(
        "flex h-[18px] min-w-[22px] items-center justify-center rounded px-1 font-mono text-[10px] font-semibold",
        fixed ? "bg-zinc-100 text-zinc-500" : proposed ? "border border-dashed border-blue-300 text-blue-600" : "bg-blue-50 text-blue-600",
      )}>
        L{node.level}
      </span>
      <span className={cn(
        "min-w-0 truncate text-[13px]",
        node.level === 1 ? "font-semibold text-zinc-900" : node.level === 2 ? "font-medium text-zinc-800" : "text-zinc-800",
        proposed && "italic text-blue-700",
        inactive && "line-through",
      )}>
        {node.label}
      </span>
      {fixed ? (
        <Lock className="size-3 shrink-0 text-zinc-300" />
      ) : node.source === "manual" ? (
        <UserPen className="size-3 shrink-0 text-zinc-400" />
      ) : (
        <Sparkles className="size-3 shrink-0 text-blue-400" />
      )}
      {proposed && <Badge tone="dashed">Proposed</Badge>}
      {merge && <Badge tone="amber"><GitMerge />Merge</Badge>}
      {split && <Badge tone="amber"><Split />Split</Badge>}
      {inactive && <Badge tone="neutral">{node.status}</Badge>}
      <span className="ml-auto flex items-center gap-2 pl-2">
        {node.level === 2 && node.candidate_count > 0 && (
          <Tip content="Extracted intents in this L2 not yet grouped into an L3/L4 category">
            <span className="rounded-full bg-zinc-50 px-1.5 text-[11px] text-zinc-400 ring-1 ring-zinc-200">{node.candidate_count} open</span>
          </Tip>
        )}
        <Tip content={`${node.interaction_count} interactions · ${node.intent_count} intents`}>
          <span key={node.interaction_count} className={cn("inline-block min-w-6 text-right font-mono text-xs tabular-nums", node.interaction_count ? "text-zinc-700 animate-bump" : "text-zinc-300")}>
            {node.interaction_count}
          </span>
        </Tip>
      </span>
    </div>
  );
});
