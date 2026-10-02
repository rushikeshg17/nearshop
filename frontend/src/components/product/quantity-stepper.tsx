"use client";

import { Minus, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";

export function QuantityStepper({ value, onChange, max, min = 1 }: { value: number; onChange: (v: number) => void; max: number; min?: number }) {
  return (
    <div className="inline-flex items-center rounded-xl border" role="group" aria-label="Quantity">
      <Button variant="ghost" size="icon-lg" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} aria-label="Decrease quantity">
        <Minus />
      </Button>
      <span className="w-10 text-center font-semibold tabular" aria-live="polite">
        {value}
      </span>
      <Button variant="ghost" size="icon-lg" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} aria-label="Increase quantity">
        <Plus />
      </Button>
    </div>
  );
}
