"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, Loader2, Store, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ResponsiveDialog } from "@/components/common/responsive-dialog";
import { QuantityStepper } from "@/components/product/quantity-stepper";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { ProductDetail, Reservation } from "@/lib/types";

export function ReserveDialog({ product, open, onOpenChange }: { product: ProductDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const max = Math.max(1, Math.min(product.quantity, 20));

  const reserve = useMutation({
    mutationFn: () => api.post<Reservation>("/reservations", { product_id: product.id, quantity: qty, note: note || null }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["product", product.id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`Reservation ${r.code} sent to ${product.shop.name}`, { description: "You'll be notified the moment they confirm." });
      onOpenChange(false);
      router.push(`/account/reservations/${r.id}`);
    },
  });

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Reserve for pickup"
      description={`${product.shop.name} will set it aside for you. No payment now.`}
      footer={
        <Button size="lg" className="h-11 w-full bg-brand text-brand-foreground hover:bg-brand/90" onClick={() => reserve.mutate()} disabled={reserve.isPending}>
          {reserve.isPending ? <Loader2 className="animate-spin" /> : <Check />}
          Reserve {qty > 1 ? `${qty} units` : "it"} · {formatPrice(product.price * qty)}
        </Button>
      }
    >
      <div className="space-y-5 pb-2">
        <div className="flex items-center justify-between gap-4 rounded-xl bg-muted/60 p-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{product.name}</p>
            <p className="text-xs text-muted-foreground">{formatPrice(product.price)} each · {product.quantity} in stock</p>
          </div>
          <QuantityStepper value={qty} onChange={setQty} max={max} />
        </div>

        <ol className="space-y-3 text-sm">
          {[
            { icon: Store, t: "The shop checks the shelf", d: "Usually within a few minutes. You get a notification." },
            { icon: Clock3, t: `Held for ${product.shop.hold_minutes} minutes`, d: "Once confirmed, walk in any time before the timer ends." },
            { icon: Wallet, t: "Inspect, then pay at the counter", d: "Cash or UPI at the shop. Nothing is charged online." },
          ].map((s, i) => (
            <li key={s.t} className="flex gap-3">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand-ink tabular">{i + 1}</span>
              <span>
                <span className="block font-medium">{s.t}</span>
                <span className="text-muted-foreground">{s.d}</span>
              </span>
            </li>
          ))}
        </ol>

        <div className="space-y-1.5">
          <Label htmlFor="res-note">Note for the shop (optional)</Label>
          <Textarea
            id="res-note"
            value={note}
            onChange={(e) => setNote(e.target.value.slice(0, 300))}
            placeholder="e.g. Size 8 please, or I'll come by 6 pm"
            rows={2}
          />
        </div>
      </div>
    </ResponsiveDialog>
  );
}
