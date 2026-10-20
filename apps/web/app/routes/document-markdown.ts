import type { Route } from "./+types/document-markdown";
import { publicMarkdown } from "../services/public-markdown.server";

export function loader({ request, params }: Route.LoaderArgs) {
  return publicMarkdown(request, params.id, params.docId);
}
