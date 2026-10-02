import Link from "next/link";

import { Logo } from "@/components/brand/logo";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col px-5 py-6 md:px-10">
        <Logo />
        <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">{children}</main>
        <p className="text-xs text-muted-foreground">
          <Link href="/" className="hover:text-foreground">Back to NearShop</Link>
        </p>
      </div>
      <aside className="relative hidden overflow-hidden bg-primary text-primary-foreground lg:block">
        <div className="bg-dots absolute inset-0 opacity-40 [mask-image:linear-gradient(to_bottom,black,transparent)]" aria-hidden />
        <div className="relative flex h-full flex-col justify-end p-12">
          <div className="max-w-md">
            <p className="font-heading text-4xl leading-tight font-semibold">Stop calling five shops for one spare part.</p>
            <p className="mt-4 text-primary-foreground/60">
              NearShop shows what local shops actually have on the shelf, how much it costs, and how recently they counted it.
            </p>
          </div>
          <div className="mt-12 grid max-w-md grid-cols-3 gap-4 text-sm">
            {[
              ["Search", "by meaning"],
              ["Reserve", "no prepayment"],
              ["Pick up", "or get delivery"],
            ].map(([a, b]) => (
              <div key={a} className="rounded-2xl bg-primary-foreground/[0.06] p-4">
                <p className="font-semibold">{a}</p>
                <p className="text-primary-foreground/60">{b}</p>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
