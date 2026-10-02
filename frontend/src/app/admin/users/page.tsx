"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";

import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";

type AdminUser = { id: number; name: string; email: string; role: string; is_active: boolean; created_at: string; last_login_at: string | null };

export default function AdminUsersPage() {
  const [role, setRole] = useState("all");
  const [text, setText] = useState("");
  const q = useDebounce(text, 250);
  const users = useQuery({
    queryKey: ["admin", "users", role, q],
    queryFn: () => api.get<AdminUser[]>("/admin/users", { role: role === "all" ? undefined : role, q, limit: 300 }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageTitle title="Users" />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name or email" className="h-9 pl-9" />
        </div>
        <Tabs value={role} onValueChange={setRole}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="customer">Customers</TabsTrigger>
            <TabsTrigger value="owner">Owners</TabsTrigger>
            <TabsTrigger value="admin">Admins</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : !users.data ? (
        <ListSkeleton />
      ) : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="hidden md:table-cell">Joined</TableHead>
                <TableHead className="hidden md:table-cell">Last sign-in</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell><p className="font-medium">{u.name}</p><p className="text-xs text-muted-foreground">{u.email}</p></TableCell>
                  <TableCell><Badge variant="secondary" className="capitalize">{u.role}</Badge></TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{formatDateTime(u.created_at)}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{u.last_login_at ? timeAgo(u.last_login_at) : "Never"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
