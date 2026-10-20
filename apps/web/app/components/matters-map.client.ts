import * as maplibre from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

// Serve the worker with the app; no CDN script, account or API key is required.
maplibre.setWorkerUrl(workerUrl);
export { maplibre };
