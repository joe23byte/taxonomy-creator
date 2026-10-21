import { useI18n } from "@/lib/i18n";
import { Badge, type Tone } from "../ui/primitives";

// labels live under "review.<status>" / "classification.<status>" in the i18n files
export const REVIEW_TONES: Record<string, Tone> = {
  pending: "neutral",
  needs_review: "amber",
  confirmed: "green",
  corrected: "blue",
  unclassified: "outline",
};

export const CLASS_TONES: Record<string, Tone> = {
  classified: "green",
  partial: "blue",
  unclassified: "amber",
  failed: "red",
  not_processed: "outline",
};

export function ReviewBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return <Badge tone={REVIEW_TONES[status] ?? "neutral"}>{status in REVIEW_TONES ? t(`review.${status}`) : status}</Badge>;
}

export function ClassificationBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return <Badge tone={CLASS_TONES[status] ?? "neutral"}>{status in CLASS_TONES ? t(`classification.${status}`) : status}</Badge>;
}
