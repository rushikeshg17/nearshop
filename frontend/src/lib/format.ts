const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inrPrecise = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const number = new Intl.NumberFormat("en-IN");

export function formatPrice(value: number | null | undefined, precise = false) {
  if (value === null || value === undefined) return "";
  return (precise && value % 1 !== 0 ? inrPrecise : inr).format(value);
}

export function formatCompactPrice(value: number) {
  return value >= 100000 ? `₹${compact.format(value)}` : inr.format(value);
}

export function formatNumber(value: number) {
  return number.format(value);
}

export function formatDistance(km: number | null | undefined) {
  if (km === null || km === undefined) return "";
  if (km < 1) return `${Math.max(50, Math.round((km * 1000) / 10) * 10)} m`;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

/** Rough walking/riding estimate for local context. */
export function travelHint(km: number | null | undefined) {
  if (km === null || km === undefined) return "";
  if (km <= 1.2) return `${Math.max(2, Math.round(km * 13))} min walk`;
  return `${Math.max(4, Math.round(km * 3.2 + 2))} min ride`;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(iso: string | null | undefined, now: number = Date.now()) {
  if (!iso) return "never";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatTime(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

/** "In stock, updated 2 minutes ago" style freshness text. */
export function freshness(iso: string | null | undefined) {
  if (!iso) return "Stock not yet confirmed";
  return `Updated ${timeAgo(iso)}`;
}

export function freshnessLevel(iso: string | null | undefined): "fresh" | "recent" | "stale" {
  if (!iso) return "stale";
  const hours = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (hours <= 6) return "fresh";
  if (hours <= 48) return "recent";
  return "stale";
}

export function pluralize(n: number, one: string, many = `${one}s`) {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}

export function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}
