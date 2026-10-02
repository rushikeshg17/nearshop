import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchView } from "./search-view";

export async function generateMetadata({ searchParams }: PageProps<"/search">): Promise<Metadata> {
  const q = (await searchParams).q;
  return { title: typeof q === "string" && q ? `${q} near you` : "Search nearby" };
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchView />
    </Suspense>
  );
}
