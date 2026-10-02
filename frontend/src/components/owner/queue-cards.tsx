"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Bike, Check, CheckCheck, MapPin, MessageSquare, PackageCheck, Phone, RotateCcw, Timer, X } from "lucide-react";
import { motion } from "motion/react";
import { toast } from "sonner";

import { ProductThumb } from "@/components/common/product-thumb";
import { Countdown, StatusBadge } from "@/components/common/status";
import { ConfirmAction } from "@/components/fulfillment/confirm-action";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDistance, formatPrice, timeAgo } from "@/lib/format";
import type { Order, Reservation } from "@/lib/types";

function useOwnerAction<T>(kind: "reservations" | "orders") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, reason }: { id: number; action: string; reason?: string | null }) =>
      api.post<T>(`/owner/${kind}/${id}/${action}`, { reason: reason ?? null }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["owner"] });
      const done: Record<string, string> = {
        confirm: "Confirmed. The customer has been notified.",
        reject: "Declined. The customer has been notified.",
        ready: "Marked ready. The customer has been told to come by.",
        complete: "Completed. Sale recorded.",
        prepare: "Marked as packing.",
        dispatch: "Out for delivery. Customer notified.",
        deliver: "Delivered. Cash collected and sale recorded.",
        fail: "Marked as failed.",
        return: "Returned to shop. Stock restored.",
        cancel: "Cancelled. Stock returned to the shelf.",
      };
      toast.success(done[v.action] ?? "Updated");
    },
  });
}

export function OwnerReservationCard({ r }: { r: Reservation }) {
  const act = useOwnerAction<Reservation>("reservations");
  const busy = act.isPending;
  const run = (action: string, reason?: string | null) => act.mutate({ id: r.id, action, reason });
  const has = (a: string) => r.actions.includes(a);

  return (
    <motion.li layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-2xl border bg-card p-4">
      <div className="flex gap-4">
        <ProductThumb icon={r.product.icon} imageUrl={r.product.image_url} alt="" size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={r.status} kind="reservation" />
            <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
            <span className="text-xs text-muted-foreground" suppressHydrationWarning>{timeAgo(r.created_at)}</span>
          </div>
          <p className="mt-1.5 font-medium">
            {r.quantity} x {r.product.name}
          </p>
          <p className="text-sm text-muted-foreground">
            {r.customer?.name}
            {r.customer?.phone && (
              <> · <a href={`tel:${r.customer.phone}`} className="inline-flex items-center gap-1 hover:text-foreground"><Phone className="size-3" />{r.customer.phone}</a></>
            )}
            {" · "}
            <span className="font-medium text-foreground tabular">{formatPrice(r.total)}</span>
          </p>
          {r.note && (
            <p className="mt-1.5 inline-flex items-start gap-1.5 rounded-lg bg-muted px-2 py-1 text-sm"><MessageSquare className="mt-0.5 size-3.5 shrink-0" /> {r.note}</p>
          )}
          {["REQUESTED", "CONFIRMED", "READY_FOR_PICKUP"].includes(r.status) && (
            <p className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-brand-ink">
              <Timer className="size-3.5" /> {r.status === "REQUESTED" ? "Respond within" : "Hold ends in"} <Countdown to={r.expires_at} />
              {r.status === "REQUESTED" && <span className="font-normal text-muted-foreground"> · {r.product.quantity_in_stock} on your shelf</span>}
            </p>
          )}
        </div>
      </div>
      {r.actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
          {has("confirm") && (
            <Button size="sm" onClick={() => run("confirm")} disabled={busy}><Check /> Confirm and hold</Button>
          )}
          {has("ready") && (
            <Button size="sm" onClick={() => run("ready")} disabled={busy}><PackageCheck /> Mark ready</Button>
          )}
          {has("complete") && (
            <Button size="sm" variant={has("ready") ? "outline" : "default"} onClick={() => run("complete")} disabled={busy}><CheckCheck /> Picked up and paid</Button>
          )}
          {has("reject") && (
            <ConfirmAction title="Decline this reservation?" description="The customer will be told and pointed to other shops." confirmLabel="Decline"
              reasonLabel="Reason for the customer" reasonPlaceholder="e.g. Last piece just sold at the counter" pending={busy}
              onConfirm={(reason) => run("reject", reason)}
              trigger={(open) => <Button size="sm" variant="ghost" onClick={open} disabled={busy}><X /> Decline</Button>} />
          )}
          {has("cancel") && (
            <ConfirmAction title="Cancel this reservation?" description="Use this when the customer didn't show up. The item goes back into stock." confirmLabel="Cancel reservation"
              reasonLabel="Reason" reasonPlaceholder="e.g. Customer did not come" pending={busy}
              onConfirm={(reason) => run("cancel", reason)}
              trigger={(open) => <Button size="sm" variant="ghost" onClick={open} disabled={busy}><Ban /> No-show</Button>} />
          )}
        </div>
      )}
    </motion.li>
  );
}

export function OwnerOrderCard({ o }: { o: Order }) {
  const act = useOwnerAction<Order>("orders");
  const busy = act.isPending;
  const run = (action: string, reason?: string | null) => act.mutate({ id: o.id, action, reason });
  const has = (a: string) => o.actions.includes(a);

  return (
    <motion.li layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={o.status} kind="order" />
        <span className="font-mono text-xs text-muted-foreground">{o.code}</span>
        <span className="text-xs text-muted-foreground" suppressHydrationWarning>{timeAgo(o.created_at)}</span>
        <span className="ml-auto font-semibold tabular">{formatPrice(o.total)} <span className="text-xs font-normal text-muted-foreground">COD</span></span>
      </div>
      <ul className="mt-3 space-y-1 text-sm">
        {o.items.map((i) => (
          <li key={i.product_id} className="flex justify-between gap-3"><span className="truncate">{i.quantity} x {i.name}</span><span className="text-muted-foreground tabular">{formatPrice(i.unit_price * i.quantity)}</span></li>
        ))}
      </ul>
      <div className="mt-3 space-y-1 rounded-xl bg-muted/60 p-3 text-sm">
        <p className="font-medium">{o.customer?.name}{o.contact_phone && <> · <a href={`tel:${o.contact_phone}`} className="hover:underline">{o.contact_phone}</a></>}</p>
        <p className="flex gap-1.5 text-muted-foreground"><MapPin className="mt-0.5 size-3.5 shrink-0" /> {o.delivery_address} · {formatDistance(o.distance_km)}</p>
        {o.note && <p className="text-muted-foreground">Note: {o.note}</p>}
        <a className="inline-flex items-center gap-1 text-xs font-medium text-info-ink hover:underline" target="_blank" rel="noreferrer"
          href={`https://www.openstreetmap.org/directions?to=${o.delivery_lat}%2C${o.delivery_lng}`}>Open route</a>
      </div>
      {o.actions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {has("confirm") && <Button size="sm" onClick={() => run("confirm")} disabled={busy}><Check /> Confirm order</Button>}
          {has("prepare") && <Button size="sm" onClick={() => run("prepare")} disabled={busy}><PackageCheck /> Start packing</Button>}
          {has("dispatch") && <Button size="sm" onClick={() => run("dispatch")} disabled={busy}><Bike /> Out for delivery</Button>}
          {has("deliver") && <Button size="sm" onClick={() => run("deliver")} disabled={busy}><CheckCheck /> Delivered, cash collected</Button>}
          {has("fail") && (
            <ConfirmAction title="Delivery failed?" confirmLabel="Mark failed" reasonLabel="What happened?" reasonRequired reasonPlaceholder="e.g. Customer not reachable" pending={busy}
              onConfirm={(reason) => run("fail", reason)} trigger={(open) => <Button size="sm" variant="ghost" onClick={open}>Couldn&apos;t deliver</Button>} />
          )}
          {has("return") && <Button size="sm" variant="outline" onClick={() => run("return")} disabled={busy}><RotateCcw /> Back in shop</Button>}
          {has("cancel") && (
            <ConfirmAction title="Cancel this order?" description="The customer is notified and any held stock goes back on the shelf." confirmLabel="Cancel order"
              reasonLabel="Reason for the customer" reasonRequired pending={busy} onConfirm={(reason) => run("cancel", reason)}
              trigger={(open) => <Button size="sm" variant="ghost" onClick={open} disabled={busy}><X /> {o.status === "PENDING" ? "Decline" : "Cancel"}</Button>} />
          )}
        </div>
      )}
    </motion.li>
  );
}
