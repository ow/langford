import { useEffect, useState, useRef, useMemo } from "react";
import type { Matter } from "../lib/types";
import { Loader2 } from "lucide-react";
import { Link } from "react-router";
import { Badge } from "./ui/badge";
import { displayTitle } from "../lib/display-text";

// Leaflet and React-Leaflet need to be imported dynamically for SSR compatibility
let MapContainer: any, TileLayer: any, Marker: any, Popup: any, L: any, useMap: any;

function ChangeView({ center, zoom }: { center: [number, number], zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom);
  }, [center, zoom, map]);
  return null;
}

export function MattersMap({
  matters,
  onMarkerClick,
  activeLocation,
  selectedAddress,
  mapCenter,
}: {
  matters: Matter[],
  onMarkerClick?: (matter: Matter, address?: string) => void,
  activeLocation?: { lat: number, lng: number },
  selectedAddress?: string | null,
  mapCenter?: { lat: number, lng: number },
}) {
  const [isClient, setIsClient] = useState(false);
  const markerRefs = useRef<Record<string, any>>({});

  useEffect(() => {
    const loadLeaflet = async () => {
      const leaflet = await import("leaflet");
      L = leaflet.default;
      
      // Fix default icon issue
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const reactLeaflet = await import("react-leaflet");
      MapContainer = reactLeaflet.MapContainer;
      TileLayer = reactLeaflet.TileLayer;
      Marker = reactLeaflet.Marker;
      Popup = reactLeaflet.Popup;
      useMap = reactLeaflet.useMap;
      
      setIsClient(true);
    };

    loadLeaflet();
  }, []);

  // Flatten all locations from all matters into a single list of markers
  const markers = useMemo(() => matters.flatMap(matter => 
    (matter.locations || []).map(loc => ({
      matter,
      lat: loc.lat,
      lng: loc.lng,
      address: loc.address
    }))
  ).filter(m => m.lat && m.lng), [matters]);

  // Brand-coloured circular markers (selected marker is larger and darker)
  const markerIcon = (active: boolean) =>
    L.divIcon({
      className: "",
      html: active
        ? '<span style="display:block;width:22px;height:22px;border-radius:9999px;background:var(--color-brand-700);border:3px solid #fff;box-shadow:0 0 0 2px var(--color-brand-700),0 2px 6px rgba(0,0,0,.3)"></span>'
        : '<span style="display:block;width:16px;height:16px;border-radius:9999px;background:var(--color-brand-500);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35)"></span>',
      iconSize: active ? [22, 22] : [16, 16],
      iconAnchor: active ? [11, 11] : [8, 8],
      popupAnchor: [0, active ? -12 : -9],
    });

  // Open popup when selectedAddress changes
  useEffect(() => {
    if (selectedAddress && markerRefs.current[selectedAddress]) {
      // Small timeout to allow the map to finish panning/zooming from ChangeView
      const timer = setTimeout(() => {
        if (markerRefs.current[selectedAddress]) {
          markerRefs.current[selectedAddress].openPopup();
        }
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [selectedAddress, markers]); 

  if (!isClient) {
    return (
      <div className="flex h-[360px] w-full items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-100 sm:h-[560px]">
        <Loader2 className="h-8 w-8 text-zinc-400 animate-spin" />
      </div>
    );
  }

  const defaultCenter: [number, number] = [mapCenter?.lat ?? 48.455, mapCenter?.lng ?? -123.44];
  const center: [number, number] = activeLocation ? [activeLocation.lat, activeLocation.lng] : defaultCenter;
  const zoom = activeLocation ? 16 : 14;

  const statusTone = (status: string): "success" | "danger" | "brand" | "muted" =>
    ["Adopted", "Completed"].includes(status)
      ? "success"
      : ["Denied", "Repealed"].includes(status)
        ? "danger"
        : status === "Active"
          ? "brand"
          : "muted";

  return (
    <div className="space-y-2">
      <div className="relative z-0 h-[360px] w-full overflow-hidden rounded-2xl border border-zinc-200 shadow-sm sm:h-[560px]">
        <MapContainer center={defaultCenter} zoom={14} style={{ height: "100%", width: "100%" }}>
          <ChangeView center={center} zoom={zoom} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {markers.map((m, idx) => {
            const active = !!selectedAddress && m.address === selectedAddress;
            return (
              <Marker
                key={`${m.matter.id}-${idx}`}
                position={[m.lat, m.lng]}
                icon={markerIcon(active)}
                zIndexOffset={active ? 1000 : 0}
                ref={(ref: any) => {
                  if (m.address) markerRefs.current[m.address] = ref;
                }}
                eventHandlers={{
                  click: () => onMarkerClick?.(m.matter, m.address)
                }}
              >
                <Popup>
                  <div className="max-w-[220px] space-y-1.5">
                    {m.address && (
                      <p className="!m-0 text-xs text-zinc-500">{m.address}</p>
                    )}
                    <h4 className="text-sm font-semibold leading-snug text-zinc-900">
                      {displayTitle(m.matter.title)}
                    </h4>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant={statusTone(m.matter.status)}>
                        {m.matter.status}
                      </Badge>
                      {m.matter.category && (
                        <span className="text-xs text-zinc-500">{m.matter.category}</span>
                      )}
                    </div>
                    {m.matter.description && (
                      <p className="!m-0 line-clamp-2 text-xs text-zinc-600">
                        {m.matter.description}
                      </p>
                    )}
                    <Link
                      to={`/matters/${m.matter.id}`}
                      className="inline-block text-xs font-semibold !text-brand-700 hover:underline"
                    >
                      View matter
                    </Link>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>

      <p className="px-1 text-xs text-zinc-500">
        {markers.length.toLocaleString()} mapped{" "}
        {markers.length === 1 ? "location" : "locations"} across{" "}
        {matters.length.toLocaleString()} {matters.length === 1 ? "matter" : "matters"}
      </p>

      {markers.length === 0 && matters.length > 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
          None of these addresses have been geocoded yet, so there's nothing to
          plot on the map.
        </div>
      )}
    </div>
  );
}
