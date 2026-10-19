import { Badge } from "../ui/badge";
import {
  normalizeMotionResult,
  OUTCOME_LABELS,
  type MotionOutcome,
} from "../../lib/motion-utils";

const OUTCOME_VARIANT: Record<
  MotionOutcome,
  "success" | "danger" | "warning" | "muted"
> = {
  passed: "success",
  failed: "danger",
  tabled: "warning",
  withdrawn: "muted",
};

/** Sentence-case motion outcome using the shared Badge tones. */
export function OutcomeBadge({
  result,
  className,
}: {
  result: string | null | undefined;
  className?: string;
}) {
  const outcome = normalizeMotionResult(result);
  if (!outcome) return null;
  return (
    <Badge variant={OUTCOME_VARIANT[outcome]} className={className}>
      {OUTCOME_LABELS[outcome]}
    </Badge>
  );
}
