// MapLibre GL 6 runs tile parsing in a module Web Worker that it loads by URL.
// Copy the worker and its shared chunk into public/ so Next serves them as static files.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules/maplibre-gl/dist");
const dest = join(root, "public/maplibre");
mkdirSync(dest, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) copyFileSync(join(src, f), join(dest, f));
console.log("maplibre worker copied to public/maplibre");
