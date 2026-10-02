"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  ShopBasicsFields,
  type ShopFormState,
  ShopLocationFields,
  ShopOperationsFields,
  shopPayload,
} from "@/components/shop/shop-form-fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMeta } from "@/hooks/use-session";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Your account", "Your shop", "Location", "Hours and delivery"];

export function ShopSignup() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: meta } = useMeta();
  const [step, setStep] = useState(0);
  const [owner, setOwner] = useState({ name: "", email: "", password: "" });
  const [shop, setShop] = useState<ShopFormState>({
    name: "", tagline: "", description: "", category_slugs: [], phone: "", address_line: "", locality: "", pincode: "",
    lat: 15.148, lng: 76.923, open_time: "9:30 AM", close_time: "9:00 PM", closed_on: "",
    offers_pickup: true, offers_delivery: false, delivery_radius_km: 4, delivery_fee: 30, free_delivery_above: "", hold_minutes: 30,
  });
  const set = <K extends keyof ShopFormState>(k: K, v: ShopFormState[K]) => setShop((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- start the pin at the city centre once known
    if (meta) setShop((s) => (s.locality ? s : { ...s, lat: meta.city.center.lat, lng: meta.city.center.lng }));
  }, [meta]);

  const submit = useMutation({
    mutationFn: () =>
      api.post<User>("/auth/register-shop", {
        owner: { ...owner, phone: shop.phone || null },
        shop: shopPayload(shop),
      }),
    meta: { silent: true },
    onSuccess: (user) => {
      qc.setQueryData(["me"], user);
      router.replace("/shop/catalog?welcome=1");
    },
  });

  const valid = [
    owner.name.trim().length >= 2 && /\S+@\S+\.\S+/.test(owner.email) && owner.password.length >= 8,
    shop.name.trim().length >= 3 && shop.category_slugs.length > 0 && /^[6-9]\d{9}$/.test(shop.phone),
    shop.address_line.trim().length >= 5 && !!shop.locality,
    true,
  ];

  return (
    <div>
      <p className="text-sm font-medium text-brand-ink">Step {step + 1} of {STEPS.length}</p>
      <h1 className="mt-1 text-3xl font-semibold">{STEPS[step]}</h1>
      <div className="mt-4 flex gap-1.5" aria-hidden>
        {STEPS.map((s, i) => (
          <span key={s} className={cn("h-1 flex-1 rounded-full transition-colors duration-300", i <= step ? "bg-brand" : "bg-muted")} />
        ))}
      </div>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid[step]) return;
          if (step < STEPS.length - 1) setStep(step + 1);
          else submit.mutate();
        }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.2 }}>
            {step === 0 && (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="oname">Your name</Label>
                  <Input id="oname" autoComplete="name" value={owner.name} onChange={(e) => setOwner({ ...owner, name: e.target.value })} className="h-11" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="oemail">Email</Label>
                  <Input id="oemail" type="email" autoComplete="email" value={owner.email} onChange={(e) => setOwner({ ...owner, email: e.target.value })} className="h-11" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="opw">Password</Label>
                  <Input id="opw" type="password" autoComplete="new-password" value={owner.password} onChange={(e) => setOwner({ ...owner, password: e.target.value })} className="h-11" />
                  <p className="text-xs text-muted-foreground">At least 8 characters</p>
                </div>
              </div>
            )}
            {step === 1 && <ShopBasicsFields s={shop} set={set} meta={meta} />}
            {step === 2 && <ShopLocationFields s={shop} set={set} meta={meta} />}
            {step === 3 && <ShopOperationsFields s={shop} set={set} />}
          </motion.div>
        </AnimatePresence>

        {submit.isError && (
          <p role="alert" className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{errorMessage(submit.error)}</p>
        )}

        <div className="mt-8 flex gap-3">
          {step > 0 && (
            <Button type="button" variant="outline" size="lg" className="h-11" onClick={() => setStep(step - 1)}>
              <ArrowLeft /> Back
            </Button>
          )}
          <Button type="submit" size="lg" className="h-11 flex-1" disabled={!valid[step] || submit.isPending}>
            {submit.isPending ? <Loader2 className="animate-spin" /> : step === STEPS.length - 1 ? <Check /> : null}
            {step === STEPS.length - 1 ? "Open my shop" : "Continue"}
            {step < STEPS.length - 1 && <ArrowRight />}
          </Button>
        </div>
      </form>
      <p className="mt-6 text-sm text-muted-foreground">
        Already listed? <Link href="/login?next=/shop" className="font-medium text-foreground underline underline-offset-4">Sign in</Link>
      </p>
    </div>
  );
}
