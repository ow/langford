import { Link, useRouteLoaderData } from "react-router";
import type { Municipality } from "../lib/types";
import { siteName } from "../lib/site-name";
import { PageHeader } from "../components/ui/page-header";

export default function Privacy() {
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const municipalityName = rootData?.municipality?.name || "Town of View Royal";
  const name = siteName(rootData?.municipality);
  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-3xl px-4 py-12">
        <PageHeader title="Privacy policy" />
        <div className="prose prose-zinc max-w-none rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8 prose-h2:text-lg prose-h2:font-semibold prose-h2:mt-8 prose-h2:mb-3">
        <p className="text-sm text-zinc-500">Last Updated: February 10, 2026</p>

        <h2>1. Data Collection</h2>
        <p>
          {name} primarily aggregates data from public records provided by
          the {municipalityName}. This includes meeting agendas, minutes, voting
          records, and public video broadcasts.
        </p>

        <h2>2. Personal Information</h2>
        <p>
          We do not collect personal information from visitors to this site
          unless you explicitly provide it (e.g., via contact forms). We use
          industry-standard cookies for session management and basic analytics.
        </p>

        <h2>3. Third Parties</h2>
        <p>
          We use Supabase for data storage and authentication, and Vimeo for
          video hosting. Please refer to their respective privacy policies for
          more information.
        </p>

        <div className="not-prose mt-8 rounded-xl border border-dashed border-zinc-300 p-4">
          <p className="text-sm text-zinc-500">
            This is a placeholder policy. Before going live, please ensure this
            accurately reflects your actual data handling practices.
          </p>
        </div>
      </div>
    </div>
    </div>
  );
}
