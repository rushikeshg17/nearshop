import { Suspense } from "react";

import { ShopView } from "./shop-view";

export default async function ShopPage({ params }: PageProps<"/shops/[slug]">) {
  const { slug } = await params;
  return (
    <Suspense>
      <ShopView slug={slug} />
    </Suspense>
  );
}
