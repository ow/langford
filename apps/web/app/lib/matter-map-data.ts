import type { Matter } from "./types";

export type MatterMapMarker = {
  key: string;
  matter: Matter;
  lat: number;
  lng: number;
  address?: string;
};

export function isMapLocation(
  location: unknown,
): location is { lat: number; lng: number; address?: unknown } {
  if (!location || typeof location !== "object") return false;
  const { lat, lng } = location as { lat?: unknown; lng?: unknown };
  return (
    typeof lat === "number" &&
    Number.isFinite(lat) &&
    Math.abs(lat) <= 85.051129 &&
    typeof lng === "number" &&
    Number.isFinite(lng) &&
    Math.abs(lng) <= 180
  );
}

export function matterMapMarkers(matters: Matter[]): MatterMapMarker[] {
  return matters.flatMap((matter) =>
    (matter.locations || []).flatMap((location, index) =>
      isMapLocation(location)
        ? [
            {
              key: `${matter.id}:${index}`,
              matter,
              lat: location.lat,
              lng: location.lng,
              address:
                typeof location.address === "string"
                  ? location.address
                  : undefined,
            },
          ]
        : [],
    ),
  );
}

// Only coordinates and an opaque key go to the client-side clustering worker.
export function markerGeoJSON(markers: MatterMapMarker[]) {
  return {
    type: "FeatureCollection" as const,
    features: markers.map((marker) => ({
      type: "Feature" as const,
      properties: { key: marker.key },
      geometry: {
        type: "Point" as const,
        coordinates: [marker.lng, marker.lat],
      },
    })),
  };
}
