import { AdminShell } from "./admin-shell";

export const metadata = { title: { default: "Admin", template: "%s · Admin" } };

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return <AdminShell>{children}</AdminShell>;
}
