"use client";

import { BadgeCheck, Clock3, Star } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useNow } from "@/hooks/use-debounce";
import { formatDistance, formatPrice, freshnessLevel, timeAgo } from "@/lib/format";
import type { StockStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function StockPill({
  status,
  quantity,
  className,
  compact = false,
}: {
  status: StockStatus;
  quantity: number;
  className?: string;
  compact?: boolean;
}) {
  const styles = {
    in_stock: "bg-success-soft text-success-ink",
    low_stock: "bg-warning-soft text-warning-ink",
    out_of_stock: "bg-muted text-muted-foreground",
  }[status];
  const dot = { in_stock: "bg-success", low_stock: "bg-warning", out_of_stock: "bg-muted-foreground/50" }[status];
  const label =
    status === "out_of_stock"
      ? "Out of stock"
      : compact
        ? `${quantity} left`
        : status === "low_stock"
          ? `Only ${quantity} left`
          : `${quantity} in stock`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap tabular",
        styles,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", dot, status === "in_stock" && "animate-pulse")} aria-hidden />
      {label}
    </span>
  );
}

/** "Updated 4 min ago": the core trust signal. */
export function Freshness({ at, className, prefix = "Updated" }: { at: string | null; className?: string; prefix?: string }) {
  const now = useNow(30_000);
  const level = freshnessLevel(at);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs whitespace-nowrap",
        level === "fresh" ? "text-success-ink" : "text-muted-foreground",
        className,
      )}
      suppressHydrationWarning
    >
      <Clock3 className="size-3" aria-hidden />
      {at ? `${prefix} ${timeAgo(at, now)}` : "Stock not confirmed yet"}
    </span>
  );
}

export function Price({
  value,
  mrp,
  className,
  size = "md",
}: {
  value: number;
  mrp?: number | null;
  className?: string;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const sizes = { sm: "text-sm", md: "text-base", lg: "text-xl", xl: "text-3xl" }[size];
  const off = mrp && mrp > value ? Math.round(((mrp - value) / mrp) * 100) : 0;
  return (
    <span className={cn("inline-flex items-baseline gap-1.5 tabular", className)}>
      <span className={cn("font-semibold tracking-tight", sizes)}>{formatPrice(value)}</span>
      {off >= 3 && (
        <>
          <span className="text-xs text-muted-foreground line-through">{formatPrice(mrp)}</span>
          <span className="text-xs font-medium text-success-ink">{off}% off MRP</span>
        </>
      )}
    </span>
  );
}

export function Rating({ value, count, className, showCount = true }: { value: number | null; count: number; className?: string; showCount?: boolean }) {
  if (!value || !count) return <span className={cn("text-xs text-muted-foreground", className)}>No reviews yet</span>;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs tabular", className)}>
      <Star className="size-3.5 fill-warning text-warning" aria-hidden />
      <span className="font-medium text-foreground">{value.toFixed(1)}</span>
      {showCount && <span className="text-muted-foreground">({count})</span>}
      <span className="sr-only">
        rated {value} out of 5 from {count} reviews
      </span>
    </span>
  );
}

export function Distance({ km, className }: { km: number | null | undefined; className?: string }) {
  if (km === null || km === undefined) return null;
  return <span className={cn("text-xs text-muted-foreground tabular whitespace-nowrap", className)}>{formatDistance(km)}</span>;
}

export function OpenBadge({ isOpen, label, className }: { isOpen: boolean | null; label: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs whitespace-nowrap",
        isOpen === true ? "text-success-ink" : isOpen === false ? "text-muted-foreground" : "text-muted-foreground",
        className,
      )}
    >
      <span
        className={cn("size-1.5 rounded-full", isOpen ? "bg-success" : "bg-muted-foreground/40")}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function VerifiedMark({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <BadgeCheck className={cn("size-4 shrink-0 text-info", className)} aria-label="Verified shop" />
      </TooltipTrigger>
      <TooltipContent>Verified by NearShop: address and owner checked in person</TooltipContent>
    </Tooltip>
  );
}
