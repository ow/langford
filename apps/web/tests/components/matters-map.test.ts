import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { MattersMap } from "../../app/components/matters-map";
import type { Matter } from "../../app/lib/types";

// The actual component must render on Workers/SSR without a DOM or WebGL and
// leave real matter links available independently of the canvas.
describe("MattersMap server fallback", () => {
  function render(matters: Matter[]) {
    return renderToStaticMarkup(
      createElement(MemoryRouter, null, createElement(MattersMap, { matters })),
    );
  }

  it("renders accessible loading state and safe location links without a browser", () => {
    const html = render([
      {
        id: 42,
        slug: "shared-address",
        title: "<script>unsafe</script>",
        locations: [
          { lat: 48.4496, lng: -123.5045, address: "123 Main Street" },
        ],
      } as Matter,
    ]);
    expect(html).toContain('role="status"');
    expect(html).toContain("Loading map…");
    expect(html).toContain('href="/matters/shared-address"');
    expect(html).toContain("123 Main Street");
    expect(html).not.toContain("<script>unsafe</script>");
  });

  it("explains when no usable locations exist", () => {
    expect(
      render([{ id: 1, locations: [{ lat: null, lng: null }] } as Matter]),
    ).toContain("nothing to plot on the map");
  });
});
