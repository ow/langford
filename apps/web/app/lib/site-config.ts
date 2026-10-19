/**
 * Fork-level defaults, used when municipality data isn't loaded (error pages,
 * meta before data). Change these when forking for another town.
 */
export const DEFAULT_MUNICIPALITY = {
  slug: "langford",
  short_name: "Langford",
  name: "City of Langford",
  province: "BC",
  /** Nominatim viewbox (minLon,minLat,maxLon,maxLat) used to bias geocoding. */
  geocodeViewBox: "-123.62,48.39,-123.45,48.50",
} as const;
