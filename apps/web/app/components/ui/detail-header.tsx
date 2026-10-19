import { ChevronLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "~/lib/utils";

interface DetailHeaderProps {
  /** Parent page; rendered as the first item of the eyebrow line. */
  back?: { to: string; label: string };
  /** Short facts shown after the back link (date, length, term…). */
  meta?: ReactNode[];
  title: ReactNode;
  /** Inline next to the title (status badges). */
  badges?: ReactNode;
  /** Right-aligned on desktop, below the title on mobile (source links, follow…). */
  actions?: ReactNode;
  /** Optional lead paragraph under the title. */
  description?: ReactNode;
  className?: string;
}

/**
 * Header for detail pages: one eyebrow line (back link · meta) above the
 * title, so context and facts never take two separate rows.
 */
export function DetailHeader({
  back,
  meta = [],
  title,
  badges,
  actions,
  description,
  className,
}: DetailHeaderProps) {
  const items = meta.filter(Boolean);
  return (
    <header className={cn("mb-8", className)}>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          {(back || items.length > 0) && (
            <p className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500">
              {back && (
                <Link
                  to={back.to}
                  className="-ml-1 inline-flex items-center font-medium text-zinc-600 hover:text-brand-700"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  {back.label}
                </Link>
              )}
              {items.map((item, i) => (
                <span key={i} className="inline-flex items-center gap-2">
                  {(back || i > 0) && (
                    <span aria-hidden="true" className="text-zinc-300">
                      ·
                    </span>
                  )}
                  {item}
                </span>
              ))}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 md:text-4xl">
              {title}
            </h1>
            {badges}
          </div>
          {description && (
            <p className="mt-2 max-w-3xl text-base leading-relaxed text-zinc-600">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </header>
  );
}
