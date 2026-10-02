"use client";

import { Package } from "lucide-react";
import { DynamicIcon, type IconName } from "lucide-react/dynamic";

import { ICONS } from "@/lib/icon-map";

function toKebab(name: string) {
  return name
    .replace(/([a-z])([A-Z0-9])/g, "$1-$2")
    .replace(/([0-9])([A-Z])/g, "$1-$2")
    .toLowerCase();
}

/** Renders a Lucide icon from a name stored in the database (e.g. "ShoppingBag").
 *  Icons used by the catalogue are bundled statically; anything else loads on demand. */
export function AppIcon({ name, className, strokeWidth = 1.75 }: { name: string; className?: string; strokeWidth?: number }) {
  const Static = ICONS[name];
  if (Static) return <Static className={className} strokeWidth={strokeWidth} aria-hidden />;
  return (
    <DynamicIcon
      name={toKebab(name) as IconName}
      className={className}
      strokeWidth={strokeWidth}
      aria-hidden
      fallback={() => <Package className={className} strokeWidth={strokeWidth} aria-hidden />}
    />
  );
}
