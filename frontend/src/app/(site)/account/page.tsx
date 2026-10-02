import type { Metadata } from "next";

import { AccountView } from "./account-view";

export const metadata: Metadata = { title: "Your activity" };

export default function AccountPage() {
  return <AccountView />;
}
