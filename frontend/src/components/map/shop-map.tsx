"use client";

import type { GeoJSONSource, Map as MLMap, Marker } from "maplibre-gl";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface MapPoint {
  id: number;
  lat: number;
  lng: number;
  label: string; // short text in the pin, e.g. a price
  title: string; // accessible name
  muted?: boolean; // e.g. only out-of-stock matches
}

const STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

function circlePolygon(lat: number, lng: number, km: number, steps = 72) {
  const coords: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    const dLat = (km / 111.32) * Math.cos(a);
    const dLng = (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.sin(a);
    coords.push([lng + dLng, lat + dLat]);
  }
  return { type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [coords] }, properties: {} };
}

/**
 * OpenStreetMap vector map (MapLibre GL + OpenFreeMap tiles) with price pins for shops.
 * Pins are HTML markers so they can be styled, focused and highlighted like any other element.
 */
export function ShopMap({
  center,
  points,
  radiusKm,
  user,
  highlighted,
  selected,
  onSelect,
  onMapClick,
  fitToPoints = true,
  zoom = 13,
  className,
  interactive = true,
}: {
  center: { lat: number; lng: number };
  points: MapPoint[];
  radiusKm?: number;
  user?: { lat: number; lng: number } | null;
  highlighted?: number[] | null;
  selected?: number | null;
  onSelect?: (id: number) => void;
  onMapClick?: (pos: { lat: number; lng: number }) => void;
  fitToPoints?: boolean;
  zoom?: number;
  className?: string;
  interactive?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<Map<number, { marker: Marker; el: HTMLButtonElement }>>(new Map());
  const userMarker = useRef<Marker | null>(null);
  const libRef = useRef<typeof import("maplibre-gl") | null>(null);
  const onSelectRef = useRef(onSelect);
  const onMapClickRef = useRef(onMapClick);
  const [loaded, setLoaded] = useState(false);
  const { resolvedTheme } = useTheme();
  const themeKey = resolvedTheme === "dark" ? "dark" : "light";

  useEffect(() => {
    onSelectRef.current = onSelect;
    onMapClickRef.current = onMapClick;
  }, [onSelect, onMapClick]);

  // Create the map once.
  useEffect(() => {
    let cancelled = false;
    const markerMap = markers.current;
    (async () => {
      const lib = await import("maplibre-gl");
      if (cancelled || !container.current) return;
      lib.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs"); // served from public/ (scripts/copy-maplibre-worker.mjs)
      libRef.current = lib;
      const m = new lib.Map({
        container: container.current,
        style: STYLES[themeKey],
        center: [center.lng, center.lat],
        zoom,
        // Small static maps show attribution as a caption instead of an overlay (still visible, as OSM requires).
        attributionControl: interactive ? { compact: true } : false,
        interactive,
        cooperativeGestures: false,
      });
      if (interactive) m.addControl(new lib.NavigationControl({ showCompass: false }), "top-right");
      // Ready as soon as the style is in: pins and clicks must not wait for every map tile to download,
      // or the map looks dead on a slow connection.
      m.once("style.load", () => !cancelled && setLoaded(true));
      m.on("click", (e) => onMapClickRef.current?.({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
      map.current = m;
    })();
    return () => {
      cancelled = true;
      markerMap.forEach(({ marker }) => marker.remove());
      markerMap.clear();
      map.current?.remove();
      map.current = null;
      setLoaded(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map is created once; later props are applied below
  }, []);

  // Switch basemap with the theme; re-add the radius layer after the style reloads.
  const firstTheme = useRef(themeKey);
  useEffect(() => {
    if (!map.current || themeKey === firstTheme.current) return;
    firstTheme.current = themeKey;
    setLoaded(false);
    map.current.setStyle(STYLES[themeKey]);
    map.current.once("styledata", () => setLoaded(true));
  }, [themeKey]);

  // Follow the centre when the map is not auto-fitting to pins (e.g. the shop-location picker).
  useEffect(() => {
    if (!map.current || !loaded || fitToPoints) return;
    map.current.easeTo({ center: [center.lng, center.lat], duration: 400 });
  }, [loaded, fitToPoints, center.lat, center.lng]);

  // Search radius circle.
  useEffect(() => {
    const m = map.current;
    if (!m || !loaded || !radiusKm) return;
    const data = { type: "FeatureCollection" as const, features: [circlePolygon(center.lat, center.lng, radiusKm)] };
    const src = m.getSource("radius") as GeoJSONSource | undefined;
    if (src) src.setData(data);
    else {
      m.addSource("radius", { type: "geojson", data });
      m.addLayer({ id: "radius-fill", type: "fill", source: "radius", paint: { "fill-color": "#e4572e", "fill-opacity": 0.05 } });
      m.addLayer({
        id: "radius-line",
        type: "line",
        source: "radius",
        paint: { "line-color": "#e4572e", "line-opacity": 0.45, "line-width": 1.5, "line-dasharray": [2, 2] },
      });
    }
  }, [loaded, center.lat, center.lng, radiusKm]);

  // "You are here" marker.
  useEffect(() => {
    const lib = libRef.current;
    const m = map.current;
    if (!lib || !m || !loaded) return;
    userMarker.current?.remove();
    if (!user) return;
    const el = document.createElement("div");
    el.className = "relative grid size-5 place-items-center";
    el.innerHTML =
      '<span class="absolute inset-0 animate-ping rounded-full bg-info/40"></span><span class="relative size-3.5 rounded-full border-2 border-white bg-info shadow"></span>';
    el.setAttribute("aria-label", "Your location");
    userMarker.current = new lib.Marker({ element: el }).setLngLat([user.lng, user.lat]).addTo(m);
  }, [loaded, user]);

  // Shop pins.
  useEffect(() => {
    const lib = libRef.current;
    const m = map.current;
    if (!lib || !m || !loaded) return;
    const next = new Set(points.map((p) => p.id));
    markers.current.forEach(({ marker }, id) => {
      if (!next.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    });
    for (const p of points) {
      let entry = markers.current.get(p.id);
      if (!entry) {
        // MapLibre owns the wrapper's classes (positioning); we style the inner button.
        const wrap = document.createElement("div");
        const el = document.createElement("button");
        el.type = "button";
        wrap.appendChild(el);
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          onSelectRef.current?.(p.id);
        });
        const marker = new lib.Marker({ element: wrap, anchor: "bottom" }).setLngLat([p.lng, p.lat]).addTo(m);
        entry = { marker, el };
        markers.current.set(p.id, entry);
      }
      entry.marker.setLngLat([p.lng, p.lat]);
      entry.el.setAttribute("aria-label", p.title);
      entry.el.textContent = p.label;
      entry.el.dataset.muted = String(!!p.muted);
    }
    if (fitToPoints && points.length) {
      const b = new lib.LngLatBounds();
      points.forEach((p) => b.extend([p.lng, p.lat]));
      if (user) b.extend([user.lng, user.lat]);
      m.fitBounds(b, { padding: { top: 60, bottom: 60, left: 50, right: 50 }, maxZoom: 15, duration: 600 });
    }
  }, [loaded, points, fitToPoints, user]);

  // Highlight / selection styling.
  useEffect(() => {
    markers.current.forEach(({ el, marker }, id) => {
      const hot = id === selected || !!highlighted?.includes(id);
      el.className = cn(
        "rounded-full border px-2 py-1 text-xs font-semibold whitespace-nowrap shadow-md transition-all duration-150 tabular focus-visible:ring-3 focus-visible:ring-ring/60 focus-visible:outline-none",
        hot
          ? "z-10 scale-110 border-transparent bg-brand text-brand-foreground"
          : el.dataset.muted === "true"
            ? "border-border bg-muted text-muted-foreground"
            : "border-border bg-card text-foreground hover:bg-primary hover:text-primary-foreground",
      );
      marker.getElement().style.zIndex = hot ? "10" : "1";
    });
  }, [highlighted, selected, points, loaded]);

  return (
    <div className={cn("relative overflow-hidden bg-muted", className)}>
      <div ref={container} className="size-full" />
      {!loaded && <div className="absolute inset-0 animate-pulse bg-muted" aria-hidden />}
      {!interactive && (
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
          className="absolute right-1.5 bottom-1 rounded bg-background/70 px-1 text-[9px] text-muted-foreground"
        >
          © OpenStreetMap
        </a>
      )}
    </div>
  );
}
