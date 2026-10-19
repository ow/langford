import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";
import {
  normalizeMotionResult,
  OUTCOME_LABELS,
  type MotionOutcome,
} from "../lib/motion-utils";

const OUTCOME_VARIANT: Record<MotionOutcome, "success" | "danger" | "warning" | "muted"> = {
  passed: "success",
  failed: "danger",
  tabled: "warning",
  withdrawn: "muted",
};

interface MotionOutcomeBadgeProps {
  result: string | null | undefined;
  showVoteCounts?: boolean;
  yesVotes?: number;
  noVotes?: number;
  className?: string;
}

/**
 * Shared badge component for displaying motion outcomes.
 *
 * Normalizes raw database result strings (e.g. "CARRIED", "DEFEATED", "CARRRIED")
 * into sentence-case badges using the shared tones: success (passed),
 * danger (failed), warning (tabled), muted (withdrawn).
 *
 * Returns null if the result cannot be normalized (null, undefined, unknown value).
 */
export function MotionOutcomeBadge({
  result,
  showVoteCounts = false,
  yesVotes,
  noVotes,
  className,
}: MotionOutcomeBadgeProps) {
  const outcome = normalizeMotionResult(result);
  if (!outcome) return null;

  return (
    <Badge variant={OUTCOME_VARIANT[outcome]} className={cn(className)}>
      {OUTCOME_LABELS[outcome]}
      {showVoteCounts && yesVotes != null && yesVotes > 0 && (
        <span className="ml-1 opacity-80">
          ({yesVotes}-{noVotes ?? 0})
        </span>
      )}
    </Badge>
  );
}
