"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bike, Loader2, MapPin } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ResponsiveDialog } from "@/components/common/responsive-dialog";
import { LocationPicker } from "@/components/site/location-picker";
import { QuantityStepper } from "@/components/product/quantity-stepper";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useMe } from "@/hooks/use-session";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { formatDistance, formatPrice } from "@/lib/format";
import { useLocation } from "@/lib/location";
import type { DeliveryQuote, Order, ProductDetail } from "@/lib/types";

export function DeliveryDialog({ product, open, onOpenChange }: { product: ProductDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { location } = useLocation();
  const [qty, setQty] = useState(1);
  const [address, setAddress] = useState(location?.source === "locality" ? `, ${location.label}` : "");
  const [phone, setPhone] = useState(me?.phone ?? "");
  const [note, setNote] = useState("");
  const dq = useDebounce(qty, 250);

  const quote = useQuery({
    queryKey: ["quote", product.id, dq, location?.lat, location?.lng],
    queryFn: () =>
      api.post<DeliveryQuote>("/orders/quote", { items: [{ product_id: product.id, quantity: dq }], lat: location!.lat, lng: location!.lng }),
    enabled: open && !!location,
  });

  const place = useMutation({
    mutationFn: () =>
      api.post<Order>("/orders", {
        items: [{ product_id: product.id, quantity: qty }],
        lat: location!.lat,
        lng: location!.lng,
        address,
        phone,
        note: note || null,
      }),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ["product", product.id] });
      toast.success(`Order ${o.code} sent to ${product.shop.name}`, { description: "Pay cash when it arrives." });
      onOpenChange(false);
      router.push(`/account/orders/${o.id}`);
    },
  });

  const q = quote.data;
  const phoneOk = /^[6-9]\d{9}$/.test(phone);
  const canSubmit = q?.eligible && address.trim().length >= 8 && phoneOk && !place.isPending;

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Request delivery"
      description={`${product.shop.name} delivers this themselves. Cash on delivery.`}
      footer={
        <Button size="lg" className="h-11 w-full" disabled={!canSubmit} onClick={() => place.mutate()}>
          {place.isPending ? <Loader2 className="animate-spin" /> : <Bike />}
          Place order{q?.eligible && q.subtotal !== undefined ? ` · ${formatPrice((q.subtotal ?? 0) + (q.delivery_fee ?? 0))}` : ""}
        </Button>
      }
    >
      <div className="space-y-4 pb-2">
        <div className="flex items-center justify-between gap-4 rounded-xl bg-muted/60 p-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{product.name}</p>
            <p className="text-xs text-muted-foreground">{formatPrice(product.price)} each</p>
          </div>
          <QuantityStepper value={qty} onChange={setQty} max={Math.max(1, Math.min(product.quantity, 20))} />
        </div>

        <div className="space-y-1.5">
          <Label className="flex items-center gap-1.5"><MapPin className="size-3.5" /> Deliver near</Label>
          <LocationPicker className="w-full justify-start" />
        </div>

        {quote.isLoading ? (
          <div className="h-16 animate-pulse rounded-xl bg-muted" />
        ) : q && !q.eligible ? (
          <p className="rounded-xl bg-warning-soft p-3 text-sm text-warning-ink">{q.reason}. Try pickup instead, or change the delivery location.</p>
        ) : q ? (
          <dl className="space-y-1.5 rounded-xl border p-3 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">Items</dt><dd className="tabular">{formatPrice(q.subtotal ?? 0)}</dd></div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Delivery ({formatDistance(q.distance_km)})</dt>
              <dd className="tabular">{q.delivery_fee ? formatPrice(q.delivery_fee) : "Free"}</dd>
            </div>
            {q.free_delivery_above && (q.delivery_fee ?? 0) > 0 && (
              <p className="text-xs text-muted-foreground">Free delivery on orders above {formatPrice(q.free_delivery_above)}</p>
            )}
            <div className="flex justify-between border-t pt-1.5 font-semibold">
              <dt>Pay on delivery</dt>
              <dd className="tabular">{formatPrice((q.subtotal ?? 0) + (q.delivery_fee ?? 0))}</dd>
            </div>
          </dl>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="addr">Full address</Label>
          <Textarea id="addr" rows={2} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="House no., street, landmark" />
        </div>
        <div className="grid grid-cols-[1fr_1.4fr] gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="phone">Phone</Label>
            <Input
              id="phone"
              inputMode="numeric"
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
              aria-invalid={phone.length > 0 && !phoneOk}
              placeholder="10 digits"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dnote">Note (optional)</Label>
            <Input id="dnote" value={note} onChange={(e) => setNote(e.target.value.slice(0, 300))} placeholder="Call before coming" />
          </div>
        </div>
      </div>
    </ResponsiveDialog>
  );
}
