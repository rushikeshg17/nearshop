"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Loader2, Save } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { ShopAvatar } from "@/components/shop/shop-card";
import {
  parseHours,
  ShopBasicsFields,
  type ShopFormState,
  ShopLocationFields,
  ShopOperationsFields,
  shopPayload,
} from "@/components/shop/shop-form-fields";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import type { ShopDetail } from "@/lib/types";

function toForm(s: ShopDetail): ShopFormState {
  return {
    name: s.name,
    tagline: s.tagline ?? "",
    description: s.description ?? "",
    category_slugs: s.categories,
    phone: s.phone ?? "",
    address_line: s.address_line,
    locality: s.locality ?? "",
    pincode: s.pincode ?? "",
    lat: s.lat,
    lng: s.lng,
    ...parseHours(s.opening_hours),
    closed_on: s.closed_on ?? "",
    offers_pickup: s.offers_pickup,
    offers_delivery: s.offers_delivery,
    delivery_radius_km: s.delivery_radius_km || 4,
    delivery_fee: s.delivery_fee,
    free_delivery_above: s.free_delivery_above ? String(s.free_delivery_above) : "",
    hold_minutes: s.hold_minutes,
  };
}

export default function ShopSettingsPage() {
  const shop = useQuery({ queryKey: ["owner", "shop"], queryFn: () => api.get<ShopDetail>("/owner/shop") });
  if (shop.isError) return <ErrorState error={shop.error} onRetry={() => shop.refetch()} />;
  if (!shop.data) return <ListSkeleton rows={4} />;
  return <SettingsForm key={shop.data.id} initial={shop.data} />;
}

function SettingsForm({ initial }: { initial: ShopDetail }) {
  const qc = useQueryClient();
  const { data: meta } = useMeta();
  const [form, setForm] = useState<ShopFormState>(() => toForm(initial));
  const [active, setActive] = useState(initial.is_active);
  const fileRef = useRef<HTMLInputElement>(null);

  const save = useMutation({
    mutationFn: () => api.patch<ShopDetail>("/owner/shop", { ...shopPayload(form), offers_pickup: form.offers_pickup, is_active: active }),
    onSuccess: (s) => {
      qc.setQueryData(["owner", "shop"], s);
      qc.invalidateQueries({ queryKey: ["me"] });
      toast.success("Shop settings saved");
    },
  });
  const upload = useMutation({
    mutationFn: (f: File) => api.upload<{ image_url: string }>("/owner/shop/image", f),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["owner", "shop"] });
      toast.success("Shop photo updated");
    },
  });

  const set = <K extends keyof ShopFormState>(k: K, v: ShopFormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
      className="pb-24"
    >
      <PageTitle title="Shop settings" description="What customers see on your shop page and in search." />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-5 rounded-2xl border bg-card p-5">
          <div className="flex items-center gap-4">
            <ShopAvatar shop={initial} categories={meta?.categories} className="size-16" />
            <div>
              <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
                {upload.isPending ? <Loader2 className="animate-spin" /> : <Camera />} Shop photo
              </Button>
              <p className="mt-1 text-xs text-muted-foreground">A clear photo of your shopfront helps customers find you.</p>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
            </div>
          </div>
          <ShopBasicsFields s={form} set={set} meta={meta} />
          <div className="space-y-1.5">
            <Label htmlFor="desc">About your shop</Label>
            <Textarea id="desc" rows={3} value={form.description} onChange={(e) => set("description", e.target.value.slice(0, 1000))} />
          </div>
        </section>
        <section className="space-y-5 rounded-2xl border bg-card p-5">
          <ShopLocationFields s={form} set={set} meta={meta} />
        </section>
        <section className="space-y-5 rounded-2xl border bg-card p-5">
          <ShopOperationsFields s={form} set={set} />
        </section>
        <section className="space-y-5 rounded-2xl border bg-card p-5">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="pickup" className="flex flex-col items-start gap-0.5">
              <span>Accept pickup reservations</span>
              <span className="text-xs font-normal text-muted-foreground">Customers reserve and pay at your counter.</span>
            </Label>
            <Switch id="pickup" checked={form.offers_pickup} onCheckedChange={(v) => set("offers_pickup", v)} />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="active" className="flex flex-col items-start gap-0.5">
              <span>Shop visible on NearShop</span>
              <span className="text-xs font-normal text-muted-foreground">Turn off to pause while you are away. Nothing is deleted.</span>
            </Label>
            <Switch id="active" checked={active} onCheckedChange={setActive} />
          </div>
        </section>
      </div>
      <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 p-3 backdrop-blur lg:left-[248px]">
        <div className="mx-auto flex max-w-6xl justify-end px-1 md:px-3">
          <Button type="submit" disabled={save.isPending}>{save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save changes</Button>
        </div>
      </div>
    </form>
  );
}
