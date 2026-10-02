"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";

import { ResponsiveDialog } from "@/components/common/responsive-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/** A button that asks for confirmation (and optionally a reason) before an irreversible action. */
export function ConfirmAction({
  trigger,
  title,
  description,
  confirmLabel,
  reasonLabel,
  reasonPlaceholder,
  reasonRequired = false,
  destructive = true,
  pending,
  onConfirm,
  open: openProp,
  onOpenChange,
}: {
  trigger?: (open: () => void) => React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel: string;
  reasonLabel?: string;
  reasonPlaceholder?: string;
  reasonRequired?: boolean;
  destructive?: boolean;
  pending?: boolean;
  onConfirm: (reason: string | null) => void;
}) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = onOpenChange ?? setOpenState;
  const [reason, setReason] = useState("");
  return (
    <>
      {trigger?.(() => setOpen(true))}
      <ResponsiveDialog
        open={open}
        onOpenChange={setOpen}
        title={title}
        description={description}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Keep it</Button>
            <Button
              variant={destructive ? "destructive" : "default"}
              disabled={pending || (reasonRequired && !reason.trim())}
              onClick={() => {
                onConfirm(reason.trim() || null);
                setOpen(false);
              }}
            >
              {pending && <Loader2 className="animate-spin" />} {confirmLabel}
            </Button>
          </>
        }
      >
        {reasonLabel ? (
          <div className="space-y-1.5 pb-2">
            <Label htmlFor="reason">{reasonLabel}</Label>
            <Textarea id="reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value.slice(0, 300))} placeholder={reasonPlaceholder} />
          </div>
        ) : (
          <div />
        )}
      </ResponsiveDialog>
    </>
  );
}
