"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Banknote, MapPin, Phone, Star, X } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ProductThumb } from "@/components/common/product-thumb";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status";
import { ConfirmAction } from "@/components/fulfillment/confirm-action";
import { EventTimeline, FulfillmentProgress } from "@/components/fulfillment/progress";
import { ReviewDialog } from "@/components/fulfillment/review-dialog";
import { ShopMap } from "@/components/map/shop-map";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDistance, formatPrice } from "@/lib/format";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";

const HEADLINE: Record<string, string> = {
  PENDING: "Waiting for the shop to confirm",
  SHOP_CONFIRMED: "Confirmed, items set aside",
  PREPARING: "Packing your order",
  OUT_FOR_DELIVERY: "On the way to you",
  DELIVERED: "Delivered",
  CANCELLED: "Order cancelled",
  DELIVERY_FAILED: "Delivery attempt failed",
  RETURNED_TO_SHOP: "Returned to the shop",
};

export function OrderView({ id }: { id: number }) {
  const qc = useQueryClient();
  const [reviewOpen, setReviewOpen] = useState(false);
  const q = useQuery({
    queryKey: ["order", id],
    queryFn: () => api.get<Order>(`/orders/${id}`),
    refetchInterval: (query) => (["PENDING", "SHOP_CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY"].includes(query.state.data?.status ?? "") ? 10_000 : false),
  });
  const cancel = useMutation({
    mutationFn: (reason: string | null) => api.post<Order>(`/orders/${id}/cancel`, { reason }),
    onSuccess: (o) => {
      qc.setQueryData(["order", id], o);
      toast.success("Order cancelled");
    },
  });

  if (q.isError) return <div className="mx-auto max-w-3xl px-4 py-12"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const o = q.data;
  if (!o) return <div className="mx-auto max-w-3xl px-4 py-12"><ListSkeleton rows={3} /></div>;
  const moving = o.status === "OUT_FOR_DELIVERY";

  return (
    <div className="mx-auto max-w-5xl px-4 pt-6 md:px-6 md:pt-10">
      <Link href="/account" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Your activity
      </Link>
      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <motion.section key={o.status} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className={cn("rounded-3xl border p-6", moving ? "border-brand/30 bg-brand-soft/50" : "bg-card")}>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={o.status} kind="order" />
              <span className="font-mono text-xs text-muted-foreground">{o.code}</span>
            </div>
            <h1 className="mt-3 text-2xl font-semibold md:text-3xl">{HEADLINE[o.status]}</h1>
            {o.close_reason && <p className="mt-1 text-muted-foreground">Reason: {o.close_reason}</p>}
            {moving && <p className="mt-1 text-muted-foreground">Keep {formatPrice(o.total)} ready. {o.shop.name} is delivering it themselves.</p>}
            <FulfillmentProgress item={o} className="mt-8" />
          </motion.section>

          <section className="rounded-3xl border bg-card p-5">
            <ul className="divide-y">
              {o.items.map((i) => (
                <li key={i.product_id} className="flex items-center gap-3 py-3 first:pt-0">
                  <ProductThumb icon={i.icon} imageUrl={i.image_url} alt="" size="sm" />
                  <Link href={`/product/${i.product_id}`} className="min-w-0 flex-1 truncate text-sm font-medium hover:underline">{i.name}</Link>
                  <span className="text-sm text-muted-foreground tabular">{i.quantity} x {formatPrice(i.unit_price)}</span>
                </li>
              ))}
            </ul>
            <dl className="mt-3 space-y-1.5 border-t pt-3 text-sm">
              <div className="flex justify-between"><dt className="text-muted-foreground">Items</dt><dd className="tabular">{formatPrice(o.subtotal)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">Delivery ({formatDistance(o.distance_km)})</dt><dd className="tabular">{o.delivery_fee ? formatPrice(o.delivery_fee) : "Free"}</dd></div>
              <div className="flex justify-between font-semibold"><dt className="inline-flex items-center gap-1.5"><Banknote className="size-4" /> {o.payment_status === "paid" ? "Paid on delivery" : "Pay on delivery"}</dt><dd className="tabular">{formatPrice(o.total)}</dd></div>
            </dl>
          </section>

          <div className="flex flex-wrap gap-2">
            {o.actions.includes("cancel") && (
              <ConfirmAction title="Cancel this order?" description="The shop will be notified straight away." confirmLabel="Cancel order"
                reasonLabel="Reason (optional)" pending={cancel.isPending} onConfirm={(r) => cancel.mutate(r)}
                trigger={(open) => <Button variant="outline" onClick={open}><X /> Cancel order</Button>} />
            )}
            {o.status === "DELIVERED" && !o.reviewed && <Button onClick={() => setReviewOpen(true)}><Star /> Rate this delivery</Button>}
          </div>

          {o.timeline && (
            <section className="rounded-3xl border bg-card p-5">
              <h2 className="mb-4 font-semibold">Timeline</h2>
              <EventTimeline events={o.timeline} />
            </section>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <div className="overflow-hidden rounded-3xl border bg-card">
            <div className="h-48">
              <ShopMap className="h-full" center={o.shop} interactive={false}
                points={[
                  { id: o.shop.id, lat: o.shop.lat, lng: o.shop.lng, label: o.shop.name, title: o.shop.name },
                  { id: -1, lat: o.delivery_lat, lng: o.delivery_lng, label: "You", title: "Delivery address" },
                ]} selected={-1} />
            </div>
            <div className="space-y-3 p-5 text-sm">
              <p className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" /> {o.delivery_address}</p>
              <div className="flex items-center justify-between gap-2 border-t pt-3">
                <Link href={`/shops/${o.shop.slug}`} className="font-medium hover:underline">{o.shop.name}</Link>
                {o.shop.phone && <Button asChild size="sm" variant="outline"><a href={`tel:${o.shop.phone}`}><Phone /> Call shop</a></Button>}
              </div>
            </div>
          </div>
        </aside>
      </div>
      {reviewOpen && <ReviewDialog item={o} open onOpenChange={setReviewOpen} />}
    </div>
  );
}
