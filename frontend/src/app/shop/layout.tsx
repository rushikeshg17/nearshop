import { OwnerShell } from "./owner-shell";

export const metadata = { title: { default: "Shop dashboard", template: "%s · Shop dashboard" } };

export default function OwnerLayout({ children }: LayoutProps<"/shop">) {
  return <OwnerShell>{children}</OwnerShell>;
}
