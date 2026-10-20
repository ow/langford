import { describe, expect, it } from "vitest";
import {
  isMapLocation,
  markerGeoJSON,
  matterMapMarkers,
} from "../../app/lib/matter-map-data";
import type { Matter } from "../../app/lib/types";

// These protect the stored-data -> GeoJSON contract: longitude must come first,
// unusable coordinates must not break the source, and shared-address matters
// must retain distinct identities so their individual links stay reachable.
describe("matter map data", () => {
  const matter = (id: number, locations: unknown[]) =>
    ({ id, title: `Matter ${id}`, locations }) as Matter;

  it("keeps stored coordinates, shared locations and matter identities", () => {
    const markers = matterMapMarkers([
      matter(1, [{ lat: 48.4496, lng: -123.5045, address: "Langford" }]),
      matter(2, [{ lat: 48.4496, lng: -123.5045, address: "Langford" }]),
    ]);
    const geojson = markerGeoJSON(markers);
    expect(
      geojson.features.map((feature) => feature.geometry.coordinates),
    ).toEqual([
      [-123.5045, 48.4496],
      [-123.5045, 48.4496],
    ]);
    expect(
      new Set(geojson.features.map((feature) => feature.properties.key)).size,
    ).toBe(2);
    expect(markers.map((marker) => [marker.matter.id, marker.address])).toEqual(
      [
        [1, "Langford"],
        [2, "Langford"],
      ],
    );
  });

  it("accepts zero coordinates while excluding absent, nonfinite and out-of-projection points", () => {
    const markers = matterMapMarkers([
      matter(1, [
        null,
        {},
        { lat: null, lng: 0 },
        { lat: "48", lng: -123 },
        { lat: NaN, lng: 1 },
        { lat: 90, lng: 1 },
        { lat: 48, lng: 181 },
        { lat: 48, lng: Infinity },
        { lat: 0, lng: 0 },
      ]),
    ]);
    expect(markers.map(({ lat, lng }) => [lat, lng])).toEqual([[0, 0]]);
    expect(isMapLocation(undefined)).toBe(false);
  });

  it("supports filtering to no results and missing location arrays", () => {
    expect(markerGeoJSON(matterMapMarkers([{ id: 1 } as Matter]))).toEqual({
      type: "FeatureCollection",
      features: [],
    });
    expect(matterMapMarkers([])).toEqual([]);
  });
});
