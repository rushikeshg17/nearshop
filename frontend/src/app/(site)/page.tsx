import type { Metadata } from "next";
import { Suspense } from "react";

import { HomeView } from "./home-view";

export const metadata: Metadata = { title: { absolute: "NearShop: find it nearby" } };

export default function HomePage() {
  return (
    <Suspense>
      <HomeView />
    </Suspense>
  );
}
