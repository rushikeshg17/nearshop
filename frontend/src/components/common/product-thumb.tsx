import { AppIcon } from "@/components/common/app-icon";
import { cn } from "@/lib/utils";

const CATEGORY_HUES: Record<string, number> = {};

export function registerCategoryHues(categories: { slug: string; color_hue: number }[]) {
  for (const c of categories) CATEGORY_HUES[c.slug] = c.color_hue;
}

/** Product image, or a calm tinted tile with the item's icon when the shop has not uploaded a photo. */
export function ProductThumb({
  icon,
  imageUrl,
  category,
  hue,
  alt,
  size = "md",
  className,
}: {
  icon: string;
  imageUrl?: string | null;
  category?: string | null;
  hue?: number;
  alt: string;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const h = hue ?? (category ? CATEGORY_HUES[category] : undefined) ?? 60;
  const sizes = {
    sm: "size-11 rounded-lg [&_svg]:size-5",
    md: "size-16 rounded-xl [&_svg]:size-7",
    lg: "size-24 rounded-2xl [&_svg]:size-10",
    xl: "aspect-square w-full rounded-3xl [&_svg]:size-24",
  }[size];

  if (imageUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- images come from the API via /media proxy
      <img src={imageUrl} alt={alt} loading="lazy" className={cn(sizes, "shrink-0 bg-muted object-cover", className)} />
    );
  }
  return (
    <div
      role="img"
      aria-label={alt}
      className={cn(sizes, "grid shrink-0 place-items-center", className)}
      style={{
        background: `light-dark(oklch(0.955 0.028 ${h}), oklch(0.27 0.035 ${h}))`,
        color: `light-dark(oklch(0.5 0.11 ${h}), oklch(0.8 0.09 ${h}))`,
      }}
    >
      <AppIcon name={icon} />
    </div>
  );
}
