import type { ReactNode } from "react";
import { cn } from "~/lib/utils";

interface FilterBarProps {
  /** Usually a SearchField (grows to fill). */
  search?: ReactNode;
  /** Selects / toggles shown beside the search. */
  controls?: ReactNode;
  /** Optional line under the bar (result count, clear link). */
  status?: ReactNode;
  sticky?: boolean;
  className?: string;
}

/** Standard list-page filter row: search + controls, optionally sticky. */
export function FilterBar({ search, controls, status, sticky = true, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        "mb-6",
        sticky &&
          "sticky top-16 z-20 -mx-4 bg-zinc-50/90 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-zinc-50/75",
        className,
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {search && <div className="min-w-0 flex-1">{search}</div>}
        {controls && <div className="flex gap-2">{controls}</div>}
      </div>
      {status && <div className="mt-2 text-sm text-zinc-500">{status}</div>}
    </div>
  );
}
