"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Navigation, Phone, Search, Star, X } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ProductThumb } from "@/components/common/product-thumb";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Countdown, StatusBadge } from "@/components/common/status";
import { ConfirmAction } from "@/components/fulfillment/confirm-action";
import { EventTimeline, FulfillmentProgress } from "@/components/fulfillment/progress";
import { ReviewDialog } from "@/components/fulfillment/review-dialog";
import { ShopMap } from "@/components/map/shop-map";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { Reservation } from "@/lib/types";
import { cn } from "@/lib/utils";

const HEADLINE: Record<string, { title: string; body: (r: Reservation) => string }> = {
  REQUESTED: { title: "Waiting for the shop", body: (r) => `${r.shop.name} is checking the shelf. You'll get a notification when it's set aside.` },
  CONFIRMED: { title: "It's held for you", body: (r) => `Walk in before the timer ends and show code ${r.code} at the counter.` },
  READY_FOR_PICKUP: { title: "Ready at the counter", body: (r) => `Packed and waiting. Show code ${r.code} and pay at the shop.` },
  COMPLETED: { title: "Picked up", body: () => "Thanks for shopping local." },
  REJECTED: { title: "The shop couldn't hold it", body: (r) => r.close_reason ?? "Try another shop nearby." },
  CANCELLED: { title: "Reservation cancelled", body: (r) => r.close_reason ?? "Nothing was charged." },
  EXPIRED: { title: "Reservation expired", body: (r) => (r.confirmed_at ? "The hold time ran out and the item went back on the shelf." : "The shop didn't respond in time.") },
};

export function ReservationView({ id }: { id: number }) {
  const qc = useQueryClient();
  const [reviewOpen, setReviewOpen] = useState(false);
  const q = useQuery({
    queryKey: ["reservation", id],
    queryFn: () => api.get<Reservation>(`/reservations/${id}`),
    refetchInterval: (query) => (["REQUESTED", "CONFIRMED", "READY_FOR_PICKUP"].includes(query.state.data?.status ?? "") ? 8_000 : false),
  });
  const cancel = useMutation({
    mutationFn: (reason: string | null) => api.post<Reservation>(`/reservations/${id}/cancel`, { reason }),
    onSuccess: (r) => {
      qc.setQueryData(["reservation", id], r);
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Reservation cancelled");
    },
  });

  if (q.isError) return <div className="mx-auto max-w-3xl px-4 py-12"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const r = q.data;
  if (!r) return <div className="mx-auto max-w-3xl px-4 py-12"><ListSkeleton rows={3} /></div>;

  const live = ["REQUESTED", "CONFIRMED", "READY_FOR_PICKUP"].includes(r.status);
  const held = r.status === "CONFIRMED" || r.status === "READY_FOR_PICKUP";
  const head = HEADLINE[r.status];

  return (
    <div className="mx-auto max-w-5xl px-4 pt-6 md:px-6 md:pt-10">
      <Link href="/account" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Your activity
      </Link>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <motion.section
            key={r.status}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn("rounded-3xl border p-6", held ? "border-brand/30 bg-brand-soft/50" : "bg-card")}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <StatusBadge status={r.status} kind="reservation" />
                <h1 className="mt-3 text-2xl font-semibold md:text-3xl">{head.title}</h1>
                <p className="mt-1 max-w-md text-muted-foreground">{head.body(r)}</p>
              </div>
              {live && (
                <div className="rounded-2xl bg-card px-5 py-3 text-center shadow-soft">
                  <p className="text-xs text-muted-foreground">{r.status === "REQUESTED" ? "Shop responds within" : "Held for"}</p>
                  <p className="font-heading text-3xl font-semibold"><Countdown to={r.expires_at} expiredLabel="0:00" /></p>
                </div>
              )}
            </div>
            {held && (
              <div className="mt-6 flex items-center justify-between rounded-2xl border border-dashed border-brand/40 bg-card p-4">
                <div>
                  <p className="text-xs text-muted-foreground">Pickup code</p>
                  <p className="font-mono text-3xl font-semibold tracking-[0.2em]">{r.code.replace("R-", "")}</p>
                </div>
                <p className="max-w-40 text-right text-xs text-muted-foreground">Show this at the counter. Pay {formatPrice(r.total)} at the shop.</p>
              </div>
            )}
            <FulfillmentProgress item={r} className="mt-8" />
          </motion.section>

          <section className="flex items-center gap-4 rounded-3xl border bg-card p-5">
            <ProductThumb icon={r.product.icon} imageUrl={r.product.image_url} alt="" size="lg" />
            <div className="min-w-0 flex-1">
              <Link href={`/product/${r.product.id}`} className="font-semibold hover:underline">{r.product.name}</Link>
              <p className="text-sm text-muted-foreground">{r.quantity} x {formatPrice(r.unit_price)}{r.product.unit && ` · ${r.product.unit}`}</p>
              {r.note && <p className="mt-1 text-sm">Your note: &ldquo;{r.note}&rdquo;</p>}
            </div>
            <p className="text-lg font-semibold tabular">{formatPrice(r.total)}</p>
          </section>

          <div className="flex flex-wrap gap-2">
            {r.actions.includes("cancel") && (
              <ConfirmAction
                title="Cancel this reservation?"
                description="The shop will put the item back on the shelf."
                confirmLabel="Cancel reservation"
                reasonLabel="Reason (optional, helps the shop)"
                reasonPlaceholder="e.g. Found it elsewhere"
                pending={cancel.isPending}
                onConfirm={(reason) => cancel.mutate(reason)}
                trigger={(open) => (
                  <Button variant="outline" onClick={open}><X /> Cancel reservation</Button>
                )}
              />
            )}
            {r.status === "COMPLETED" && !r.reviewed && (
              <Button onClick={() => setReviewOpen(true)}><Star /> Rate this pickup</Button>
            )}
            {["REJECTED", "EXPIRED", "CANCELLED"].includes(r.status) && (
              <Button asChild><Link href={`/search?q=${encodeURIComponent(r.product.name)}`}><Search /> Find it at another shop</Link></Button>
            )}
          </div>

          {r.timeline && (
            <section className="rounded-3xl border bg-card p-5">
              <h2 className="mb-4 font-semibold">Timeline</h2>
              <EventTimeline events={r.timeline} />
            </section>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <div className="overflow-hidden rounded-3xl border bg-card">
            <div className="h-44">
              <ShopMap className="h-full" center={r.shop} zoom={15} fitToPoints={false} interactive={false}
                points={[{ id: r.shop.id, lat: r.shop.lat, lng: r.shop.lng, label: r.shop.name, title: r.shop.name }]} selected={r.shop.id} />
            </div>
            <div className="p-5">
              <Link href={`/shops/${r.shop.slug}`} className="font-semibold hover:underline">{r.shop.name}</Link>
              <p className="mt-0.5 text-sm text-muted-foreground">{r.shop.address_line}</p>
              <p className="mt-1 text-xs text-muted-foreground">{r.shop.hours_label}</p>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <Button asChild variant="outline" size="sm">
                  <a href={`https://www.openstreetmap.org/directions?to=${r.shop.lat}%2C${r.shop.lng}`} target="_blank" rel="noreferrer"><Navigation /> Directions</a>
                </Button>
                {r.shop.phone && (
                  <Button asChild variant="outline" size="sm"><a href={`tel:${r.shop.phone}`}><Phone /> Call</a></Button>
                )}
              </div>
            </div>
          </div>
        </aside>
      </div>
      {reviewOpen && <ReviewDialog item={r} open onOpenChange={setReviewOpen} />}
    </div>
  );
}
