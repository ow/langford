import { useState, useEffect } from "react";
import type { UnifiedSearchResult } from "../../services/hybrid-search.server";
import { ResultCard } from "./result-card";
import { Search, ChevronDown } from "lucide-react";

const PAGE_SIZE = 10;

// ---------------------------------------------------------------------------
// SearchResults component
// ---------------------------------------------------------------------------

interface SearchResultsProps {
  results: UnifiedSearchResult[];
  query: string;
  isLoading: boolean;
  activeTypes?: Array<UnifiedSearchResult["type"]>;
}

export function SearchResults({
  results,
  query,
  isLoading,
  activeTypes,
}: SearchResultsProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset visible count when results change (new search)
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [results]);

  const visibleResults = results.slice(0, visibleCount);
  const hasMore = results.length > visibleCount;

  return (
    <div className="mt-4 space-y-4">
      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="p-5 bg-white rounded-2xl border border-zinc-200 animate-pulse"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="h-4 w-4 bg-zinc-200 rounded" />
                <div className="h-4 w-20 bg-zinc-200 rounded" />
                <div className="h-4 w-24 bg-zinc-200 rounded ml-auto" />
              </div>
              <div className="space-y-2">
                <div className="h-4 bg-zinc-200 rounded w-full" />
                <div className="h-4 bg-zinc-200 rounded w-3/4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Results list */}
      {!isLoading && results.length > 0 && (
        <div className="space-y-4">
          <ul className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm divide-y divide-zinc-100">
            {visibleResults.map((result, index) => (
              <li key={`${result.type}-${result.id}`}>
                <ResultCard result={result} query={query} position={index} />
              </li>
            ))}
          </ul>

          {/* Show more button */}
          {hasMore && (
            <button
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
              className="mx-auto flex items-center justify-center gap-1.5 rounded-full border border-zinc-200 bg-white px-5 py-2 text-sm font-semibold text-zinc-700 shadow-sm transition-colors hover:border-brand-300 hover:text-brand-700"
            >
              <ChevronDown className="h-4 w-4" />
              Show more ({results.length - visibleCount} remaining)
            </button>
          )}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && results.length === 0 && (
        <div className="text-center py-16">
          <Search className="h-10 w-10 text-zinc-300 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">
            {activeTypes && activeTypes.length > 0
              ? `No results found for "${query}" with the selected filters. Try broadening your search.`
              : `No results found for "${query}". Try different keywords.`}
          </p>
        </div>
      )}
    </div>
  );
}
