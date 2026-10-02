import type { Metadata } from "next";

import { ShopSignup } from "./shop-signup";

export const metadata: Metadata = { title: "List your shop" };

export default function RegisterShopPage() {
  return <ShopSignup />;
}
