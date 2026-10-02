import type { Metadata } from "next";
import { Suspense } from "react";

import { ShopsView } from "./shops-view";

export const metadata: Metadata = { title: "Shops near you" };

export default function ShopsPage() {
  return (
    <Suspense>
      <ShopsView />
    </Suspense>
  );
}
