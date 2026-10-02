"use client";

import { useNow } from "@/hooks/use-debounce";
import type { OrderStatus, ReservationStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tone = "brand" | "info" | "success" | "warning" | "muted" | "danger";

export const RESERVATION_LABELS: Record<ReservationStatus, { label: string; tone: Tone; hint: string }> = {
  REQUESTED: { label: "Waiting for shop", tone: "warning", hint: "The shop is checking the shelf" },
  CONFIRMED: { label: "Held for you", tone: "info", hint: "Set aside at the counter" },
  READY_FOR_PICKUP: { label: "Ready for pickup", tone: "brand", hint: "Packed and waiting" },
  COMPLETED: { label: "Picked up", tone: "success", hint: "Done" },
  REJECTED: { label: "Declined by shop", tone: "danger", hint: "" },
  CANCELLED: { label: "Cancelled", tone: "muted", hint: "" },
  EXPIRED: { label: "Expired", tone: "muted", hint: "" },
};

export const ORDER_LABELS: Record<OrderStatus, { label: string; tone: Tone; hint: string }> = {
  PENDING: { label: "Waiting for shop", tone: "warning", hint: "The shop will confirm shortly" },
  SHOP_CONFIRMED: { label: "Confirmed", tone: "info", hint: "Items set aside" },
  PREPARING: { label: "Packing", tone: "info", hint: "Being packed" },
  OUT_FOR_DELIVERY: { label: "On the way", tone: "brand", hint: "Keep cash ready" },
  DELIVERED: { label: "Delivered", tone: "success", hint: "" },
  CANCELLED: { label: "Cancelled", tone: "muted", hint: "" },
  DELIVERY_FAILED: { label: "Delivery failed", tone: "danger", hint: "" },
  RETURNED_TO_SHOP: { label: "Returned to shop", tone: "muted", hint: "" },
};

const TONES: Record<Tone, string> = {
  brand: "bg-brand-soft text-brand-ink",
  info: "bg-info-soft text-info-ink",
  success: "bg-success-soft text-success-ink",
  warning: "bg-warning-soft text-warning-ink",
  muted: "bg-muted text-muted-foreground",
  danger: "bg-destructive/10 text-destructive",
};

export function StatusBadge({ status, kind, className }: { status: string; kind: "reservation" | "order"; className?: string }) {
  const map = (kind === "reservation" ? RESERVATION_LABELS : ORDER_LABELS) as Record<string, { label: string; tone: Tone }>;
  const s = map[status] ?? { label: status, tone: "muted" as Tone };
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", TONES[s.tone], className)}>
      {s.label}
    </span>
  );
}

/** Live mm:ss countdown to a deadline (reservation hold, response window). */
export function Countdown({ to, className, expiredLabel = "Time's up" }: { to: string; className?: string; expiredLabel?: string }) {
  const now = useNow(1000);
  const ms = new Date(to).getTime() - now;
  if (ms <= 0) return <span className={cn("tabular", className)}>{expiredLabel}</span>;
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const text = h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(s).padStart(2, "0")}`;
  return (
    <span className={cn("tabular", ms < 5 * 60_000 && "text-destructive", className)} suppressHydrationWarning>
      {text}
    </span>
  );
}
