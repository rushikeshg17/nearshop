"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Star } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ResponsiveDialog } from "@/components/common/responsive-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Order, Reservation } from "@/lib/types";
import { cn } from "@/lib/utils";

function StarInput({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  const [hover, setHover] = useState(0);
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm">{label}</span>
      <div className="flex" role="radiogroup" aria-label={label} onMouseLeave={() => setHover(0)}>
        {[1, 2, 3, 4, 5].map((i) => (
          <button
            key={i}
            type="button"
            role="radio"
            aria-checked={value === i}
            aria-label={`${i} star${i > 1 ? "s" : ""}`}
            onMouseEnter={() => setHover(i)}
            onClick={() => onChange(i)}
            className="p-1 transition-transform active:scale-90"
          >
            <Star className={cn("size-6 transition-colors", i <= (hover || value) ? "fill-warning text-warning" : "text-muted-foreground/40")} />
          </button>
        ))}
      </div>
    </div>
  );
}

export function ReviewDialog({ item, open, onOpenChange }: { item: Reservation | Order; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [rating, setRating] = useState(0);
  const [accuracy, setAccuracy] = useState(0);
  const [delivery, setDelivery] = useState(0);
  const [comment, setComment] = useState("");
  const isOrder = item.kind === "order";

  const submit = useMutation({
    mutationFn: () =>
      api.post("/reviews", {
        reservation_id: isOrder ? null : item.id,
        order_id: isOrder ? item.id : null,
        rating,
        accuracy_rating: accuracy || null,
        delivery_rating: isOrder && delivery ? delivery : null,
        comment: comment.trim() || null,
      }),
    onSuccess: () => {
      toast.success("Thanks! Your review helps neighbours pick the right shop.");
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: [item.kind === "order" ? "order" : "reservation", item.id] });
      onOpenChange(false);
    },
  });

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`How was ${item.shop.name}?`}
      description="Reviews are only accepted for completed purchases, one per visit."
      footer={
        <Button className="w-full" size="lg" disabled={!rating || submit.isPending} onClick={() => submit.mutate()}>
          {submit.isPending && <Loader2 className="animate-spin" />} Post review
        </Button>
      }
    >
      <div className="space-y-3 pb-2">
        <StarInput label="Overall experience" value={rating} onChange={setRating} />
        <StarInput label="Item matched the listing" value={accuracy} onChange={setAccuracy} />
        {isOrder && <StarInput label="Delivery" value={delivery} onChange={setDelivery} />}
        <div className="space-y-1.5 pt-2">
          <Label htmlFor="rv">Anything others should know? (optional)</Label>
          <Textarea id="rv" rows={3} value={comment} onChange={(e) => setComment(e.target.value.slice(0, 1000))} placeholder="Was it ready on time? Was the stock count right?" />
        </div>
      </div>
    </ResponsiveDialog>
  );
}
