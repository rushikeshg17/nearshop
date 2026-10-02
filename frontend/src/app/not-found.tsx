import { MapPinOff } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="max-w-md text-center">
        <Logo className="justify-center" />
        <div className="mx-auto mt-10 grid size-14 place-items-center rounded-2xl bg-muted"><MapPinOff className="size-6 text-muted-foreground" /></div>
        <h1 className="mt-5 text-3xl font-semibold">This page isn&apos;t nearby</h1>
        <p className="mt-2 text-muted-foreground">The link may be old, or the listing was removed. Try searching instead.</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button asChild><Link href="/search">Search nearby</Link></Button>
          <Button asChild variant="outline"><Link href="/">Home</Link></Button>
        </div>
      </div>
    </div>
  );
}
