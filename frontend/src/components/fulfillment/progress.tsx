"use client";

import { Check } from "lucide-react";
import { motion } from "motion/react";

import { formatTime } from "@/lib/format";
import type { Order, Reservation, TimelineEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const RES_STEPS = [
  { status: "REQUESTED", label: "Requested" },
  { status: "CONFIRMED", label: "Held for you" },
  { status: "READY_FOR_PICKUP", label: "Ready" },
  { status: "COMPLETED", label: "Picked up" },
];
const ORDER_STEPS = [
  { status: "PENDING", label: "Placed" },
  { status: "SHOP_CONFIRMED", label: "Confirmed" },
  { status: "PREPARING", label: "Packing" },
  { status: "OUT_FOR_DELIVERY", label: "On the way" },
  { status: "DELIVERED", label: "Delivered" },
];

/** Horizontal stepper for the happy path; side exits (cancelled, expired...) are shown by the caller. */
export function FulfillmentProgress({ item, className }: { item: Reservation | Order; className?: string }) {
  const steps = item.kind === "reservation" ? RES_STEPS : ORDER_STEPS;
  const reached = new Map<string, string>();
  for (const e of item.timeline ?? []) reached.set(e.to_status, e.at);
  let current = steps.findIndex((s) => s.status === item.status);
  if (current === -1) {
    // closed on a side path: progress stops at the last happy-path step reached
    current = Math.max(-1, ...steps.map((s, i) => (reached.has(s.status) ? i : -1)));
  }
  const failed = !steps.some((s) => s.status === item.status);

  return (
    <ol className={cn("flex items-start", className)} aria-label="Progress">
      {steps.map((s, i) => {
        const done = i < current || (i === current && (s.status === "COMPLETED" || s.status === "DELIVERED"));
        const active = i === current && !done && !failed;
        return (
          <li key={s.status} className="relative flex flex-1 flex-col items-center text-center">
            {i > 0 && (
              <span className="absolute top-3.5 right-1/2 h-0.5 w-full -translate-y-1/2 bg-muted" aria-hidden>
                <motion.span
                  className="block h-full origin-left bg-brand"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: i <= current ? 1 : 0 }}
                  transition={{ duration: 0.5, delay: i * 0.08 }}
                />
              </span>
            )}
            <span
              className={cn(
                "relative z-10 grid size-7 place-items-center rounded-full border-2 text-xs font-semibold transition-colors",
                done ? "border-brand bg-brand text-brand-foreground" : active ? "border-brand bg-card text-brand-ink" : "border-muted bg-card text-muted-foreground",
              )}
            >
              {done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
              {active && <span className="absolute inset-0 animate-ping rounded-full border-2 border-brand/50" aria-hidden />}
            </span>
            <span className={cn("mt-2 text-xs font-medium", i <= current ? "text-foreground" : "text-muted-foreground")}>{s.label}</span>
            {reached.get(s.status) && <span className="text-[11px] text-muted-foreground tabular">{formatTime(reached.get(s.status))}</span>}
          </li>
        );
      })}
    </ol>
  );
}

const STATUS_TEXT: Record<string, string> = {
  REQUESTED: "Reservation requested",
  CONFIRMED: "Shop confirmed and set it aside",
  READY_FOR_PICKUP: "Packed and ready at the counter",
  COMPLETED: "Picked up",
  REJECTED: "Shop declined",
  CANCELLED: "Cancelled",
  EXPIRED: "Expired",
  PENDING: "Order placed",
  SHOP_CONFIRMED: "Shop confirmed the order",
  PREPARING: "Packing your order",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  DELIVERY_FAILED: "Delivery attempt failed",
  RETURNED_TO_SHOP: "Returned to shop",
};
const ACTOR: Record<string, string> = { customer: "You", owner: "Shop", system: "NearShop", admin: "Admin" };

export function EventTimeline({ events, viewer = "customer" }: { events: TimelineEvent[]; viewer?: "customer" | "owner" }) {
  return (
    <ol className="relative space-y-4 border-l pl-5">
      {[...events].reverse().map((e, i) => (
        <li key={`${e.to_status}-${e.at}-${i}`} className="relative">
          <span className={cn("absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-card", i === 0 ? "bg-brand" : "bg-muted-foreground/40")} />
          <p className="text-sm font-medium">{STATUS_TEXT[e.to_status] ?? e.to_status}</p>
          <p className="text-xs text-muted-foreground">
            {formatTime(e.at)} · {viewer === "owner" && e.actor_role === "owner" ? "You" : viewer === "owner" && e.actor_role === "customer" ? "Customer" : ACTOR[e.actor_role] ?? e.actor_role}
            {e.note && <> · &ldquo;{e.note}&rdquo;</>}
          </p>
        </li>
      ))}
    </ol>
  );
}
