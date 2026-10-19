import { Link, useRouteLoaderData } from "react-router";
import type { Municipality } from "../lib/types";
import { siteName } from "../lib/site-name";

export function Footer() {
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const name = siteName(rootData?.municipality);

  return (
    <footer className="mt-auto border-t border-zinc-200 bg-white py-8 text-sm text-zinc-500">
      <div className="container mx-auto flex max-w-7xl flex-col gap-4 px-4 sm:flex-row sm:items-center sm:justify-between">
        <p>
          © {new Date().getFullYear()} {name}. An independent project built on the open-source{" "}
          <a
            href="https://github.com/kpeatt/viewroyal"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-zinc-700 underline-offset-4 hover:text-brand-700 hover:underline"
          >
            ViewRoyal.ai
          </a>
          .
        </p>
        <nav className="flex items-center gap-5" aria-label="Footer">
          <Link to="/about" className="hover:text-zinc-900">About</Link>
          <Link to="/privacy" className="hover:text-zinc-900">Privacy</Link>
          <Link to="/terms" className="hover:text-zinc-900">Terms</Link>
        </nav>
      </div>
    </footer>
  );
}
