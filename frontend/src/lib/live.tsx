import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AnalysisEvent } from "./api";

const MAX_EVENTS = 400;
const HIGHLIGHT_MS = 2600;

const TAXONOMY_KINDS = new Set([
  "category_proposed", "category_approved", "category_refined", "merge_proposed", "split_proposed",
  "proposal_accepted", "proposal_rejected", "taxonomy_edited", "matched_existing", "interaction_assigned",
  "candidate_new", "batch_refinement", "assignment_corrected", "run_completed", "info",
]);
const PROPOSAL_KINDS = new Set(["category_proposed", "category_approved", "merge_proposed", "split_proposed", "proposal_accepted", "proposal_rejected", "taxonomy_edited"]);

interface LiveState {
  events: AnalysisEvent[];
  connected: boolean;
  highlights: Record<string, { kind: string; at: number }>;
  newNodeIds: Set<string>;
  focusInteraction: (id: number | null) => void;
  focusedInteraction: number | null;
}

const LiveContext = createContext<LiveState | null>(null);

function throttle(fn: () => void, ms: number) {
  let timer: number | null = null;
  let pending = false;
  return () => {
    if (timer) { pending = true; return; }
    fn();
    timer = window.setTimeout(() => {
      timer = null;
      if (pending) { pending = false; fn(); }
    }, ms);
  };
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [highlights, setHighlights] = useState<Record<string, { kind: string; at: number }>>({});
  const [focusedInteraction, focusInteraction] = useState<number | null>(null);
  const newNodeIds = useRef(new Set<string>());

  const invalidators = useMemo(() => ({
    summary: throttle(() => qc.invalidateQueries({ queryKey: ["summary"] }), 800),
    taxonomy: throttle(() => { qc.invalidateQueries({ queryKey: ["taxonomy"] }); qc.invalidateQueries({ queryKey: ["node"] }); }, 1000),
    proposals: throttle(() => { qc.invalidateQueries({ queryKey: ["proposals"] }); qc.invalidateQueries({ queryKey: ["changes"] }); }, 1000),
    interactions: throttle(() => { qc.invalidateQueries({ queryKey: ["interactions"] }); qc.invalidateQueries({ queryKey: ["interaction"] }); }, 2500),
    curve: throttle(() => qc.invalidateQueries({ queryKey: ["curve"] }), 3000),
  }), [qc]);

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    let retry: number | null = null;
    let latest = 0;

    const handle = (ev: AnalysisEvent) => {
      latest = Math.max(latest, ev.id);
      setEvents((prev) => (prev.length && prev[0].id >= ev.id ? prev : [ev, ...prev].slice(0, MAX_EVENTS)));
      invalidators.summary();
      if (TAXONOMY_KINDS.has(ev.kind)) invalidators.taxonomy();
      if (PROPOSAL_KINDS.has(ev.kind)) invalidators.proposals();
      if (ev.conversation_id || ev.kind.startsWith("run_") || ev.kind === "batch_refinement") invalidators.interactions();
      if (ev.kind === "batch_refinement" || ev.kind === "interaction_assigned" || ev.kind.startsWith("run_")) invalidators.curve();
      if (ev.kind === "category_proposed" && ev.node_id) {
        newNodeIds.current.add(ev.node_id);
        if (ev.data?.l3_new && ev.data?.l3_id) newNodeIds.current.add(ev.data.l3_id);
      }
      const ids = [ev.node_id, ev.data?.target_id, ev.data?.l3_id].filter(Boolean) as string[];
      if (ids.length) {
        const at = Date.now();
        setHighlights((h) => {
          const next = { ...h };
          ids.forEach((id) => (next[id] = { kind: ev.kind, at }));
          return next;
        });
      }
    };

    const connect = (after: number) => {
      if (cancelled) return;
      es = new EventSource(`/api/events/stream?after=${after}`);
      es.onopen = () => setConnected(true);
      es.addEventListener("analysis", (msg) => {
        try { handle(JSON.parse((msg as MessageEvent).data)); } catch { /* ignore malformed */ }
      });
      es.onerror = () => {
        setConnected(false);
        // browser retries automatically with Last-Event-ID; recreate only if closed
        if (es && es.readyState === EventSource.CLOSED) {
          es.close();
          retry = window.setTimeout(() => connect(latest), 3000);
        }
      };
    };

    api.events(150).then((initial) => {
      if (cancelled) return;
      setEvents(initial);
      latest = initial[0]?.id ?? 0;
      connect(latest);
    }).catch(() => connect(0));

    const unsub = () => { cancelled = true; es?.close(); if (retry) clearTimeout(retry); };
    return unsub;
  }, [invalidators]);

  // expire highlights
  useEffect(() => {
    const t = window.setInterval(() => {
      const now = Date.now();
      setHighlights((h) => {
        const entries = Object.entries(h).filter(([, v]) => now - v.at < HIGHLIGHT_MS);
        return entries.length === Object.keys(h).length ? h : Object.fromEntries(entries);
      });
    }, 500);
    return () => clearInterval(t);
  }, []);

  const value = useMemo(
    () => ({ events, connected, highlights, newNodeIds: newNodeIds.current, focusInteraction, focusedInteraction }),
    [events, connected, highlights, focusedInteraction],
  );
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive outside LiveProvider");
  return ctx;
}
