"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="grid min-h-[70dvh] place-items-center px-4">
      <div className="max-w-md text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-destructive/10"><TriangleAlert className="size-6 text-destructive" /></div>
        <h1 className="mt-5 text-2xl font-semibold">Something went wrong</h1>
        <p className="mt-2 text-muted-foreground">It&apos;s on our side, not yours. Try again, and if it keeps happening, go back home.</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button onClick={reset}><RotateCcw /> Try again</Button>
          <Button asChild variant="outline"><Link href="/">Home</Link></Button>
        </div>
      </div>
    </div>
  );
}
