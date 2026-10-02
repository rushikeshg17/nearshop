import Link from "next/link";

import { cn } from "@/lib/utils";

/** NearShop mark: a location pin whose head is a shop awning. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8", className)}>
      <rect width="32" height="32" rx="9" className="fill-brand" />
      <path
        d="M16 25.5c-.4 0-.7-.2-.9-.5C12.6 21.4 9 17.6 9 13.6 9 9.7 12.1 6.5 16 6.5s7 3.2 7 7.1c0 4-3.6 7.8-6.1 11.4-.2.3-.5.5-.9.5Z"
        className="fill-brand-foreground"
      />
      <path
        d="M11.8 12.2h8.4l-.9-2.3a1 1 0 0 0-.9-.6h-4.8a1 1 0 0 0-.9.6l-.9 2.3Zm0 0c0 .9.7 1.6 1.6 1.6s1.5-.7 1.5-1.6c0 .9.7 1.6 1.6 1.6.8 0 1.5-.7 1.5-1.6 0 .9.7 1.6 1.6 1.6s1.5-.7 1.5-1.6"
        className="fill-none stroke-brand"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <rect x="14.2" y="15" width="3.6" height="3.4" rx=".6" className="fill-brand" />
    </svg>
  );
}

export function Logo({ className, href = "/", compact = false }: { className?: string; href?: string; compact?: boolean }) {
  return (
    <Link href={href} className={cn("group inline-flex items-center gap-2 rounded-lg outline-none", className)} aria-label="NearShop home">
      <LogoMark className="transition-transform duration-300 ease-[var(--ease-out-quint)] group-hover:-rotate-6" />
      {!compact && (
        <span className="font-heading text-[1.2rem] leading-none font-semibold tracking-tight">
          near<span className="text-brand">shop</span>
        </span>
      )}
    </Link>
  );
}
