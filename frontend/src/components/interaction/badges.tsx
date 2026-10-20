import { Badge, type Tone } from "../ui/primitives";

const REVIEW: Record<string, [Tone, string]> = {
  pending: ["neutral", "Pending review"],
  needs_review: ["amber", "Needs review"],
  confirmed: ["green", "Confirmed"],
  corrected: ["blue", "Corrected"],
  unclassified: ["outline", "Unclassified"],
};

const CLASS: Record<string, [Tone, string]> = {
  classified: ["green", "Classified"],
  partial: ["blue", "L1/L2 only"],
  unclassified: ["amber", "Unclassified"],
  failed: ["red", "Failed"],
  not_processed: ["outline", "Not processed"],
};

export function ReviewBadge({ status }: { status: string }) {
  const [tone, label] = REVIEW[status] ?? ["neutral", status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function ClassificationBadge({ status }: { status: string }) {
  const [tone, label] = CLASS[status] ?? ["neutral", status];
  return <Badge tone={tone}>{label}</Badge>;
}

export const REVIEW_LABELS = Object.fromEntries(Object.entries(REVIEW).map(([k, v]) => [k, v[1]]));
export const CLASS_LABELS = Object.fromEntries(Object.entries(CLASS).map(([k, v]) => [k, v[1]]));
