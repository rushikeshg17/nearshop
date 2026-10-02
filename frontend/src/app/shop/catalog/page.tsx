import { Suspense } from "react";

import { CatalogView } from "./catalog-view";

export const metadata = { title: "Add from catalogue" };

export default function CatalogPage() {
  return (
    <Suspense>
      <CatalogView />
    </Suspense>
  );
}
