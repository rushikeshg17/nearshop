import { Suspense } from "react";

import { InventoryView } from "./inventory-view";

export const metadata = { title: "Inventory" };

export default function InventoryPage() {
  return (
    <Suspense>
      <InventoryView />
    </Suspense>
  );
}
