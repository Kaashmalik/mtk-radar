"use client";
import { useActionState, useEffect, useState } from "react";
import { toast } from "sonner";
import { linkAccount, saveProfile } from "@/lib/actions/account";
import type { AccountProfile } from "@/lib/data/account";
import { selfMeasureFields, standardSizes } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";

export function LinkAccountForm() {
  const [state, action, pending] = useActionState(linkAccount, null);
  return (
    <form action={action} className="max-w-md space-y-4">
      <div>
        <Label htmlFor="name">Full name</Label>
        <Input id="name" name="name" required autoComplete="name" />
      </div>
      <div>
        <Label htmlFor="phone">WhatsApp number</Label>
        <Input id="phone" name="phone" required inputMode="tel" placeholder="0300 1234567" />
      </div>
      <div>
        <Label htmlFor="orderNo">
          A previous order number <span className="font-normal text-muted">(if you&rsquo;ve ordered before)</span>
        </Label>
        <Input id="orderNo" name="orderNo" placeholder="LC-1042" className="uppercase" />
      </div>
      {state && !state.ok && <p className="text-sm text-danger">{state.error}</p>}
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : "Continue"}
      </Button>
    </form>
  );
}

const extraFields = [
  { key: "armhole", label: "Armhole" },
  { key: "neck", label: "Neck depth" },
  { key: "bottom", label: "Trouser bottom (pancha)" },
];

export function ProfileForm({ profile, onDone }: { profile?: AccountProfile; onDone?: () => void }) {
  const [state, action, pending] = useActionState(saveProfile, null);
  useEffect(() => {
    if (!state) return;
    if (state.ok) {
      toast.success("Measurements saved");
      onDone?.();
    } else toast.error(state.error);
  }, [state, onDone]);

  return (
    <form action={action} className="space-y-5">
      <input type="hidden" name="id" value={profile?.id ?? ""} />
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor={`name-${profile?.id}`}>Profile name</Label>
          <Input id={`name-${profile?.id}`} name="name" defaultValue={profile?.name ?? ""} placeholder="Me, Ammi, Sister…" required />
        </div>
        <div>
          <Label htmlFor={`size-${profile?.id}`}>Standard size</Label>
          <Select id={`size-${profile?.id}`} name="size" defaultValue={profile?.data.size ?? ""}>
            <option value="">—</option>
            {standardSizes.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor={`fit-${profile?.id}`}>Fit</Label>
          <Select id={`fit-${profile?.id}`} name="fit" defaultValue={profile?.fit ?? "regular"}>
            <option value="slim">Slim</option>
            <option value="regular">Regular</option>
            <option value="comfort">Comfort (loose)</option>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        {[...selfMeasureFields, ...extraFields].map((f) => (
          <div key={f.key}>
            <Label htmlFor={`${f.key}-${profile?.id}`} className="text-xs">
              {f.label} <span className="font-normal text-muted">in</span>
            </Label>
            <Input id={`${f.key}-${profile?.id}`} name={f.key} inputMode="decimal" defaultValue={profile?.data[f.key] ?? ""} className="h-10" />
          </div>
        ))}
      </div>
      {profile?.verified && <p className="text-xs text-muted">This profile was verified by Laraib. Editing it will remove the verified badge.</p>}
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : "Save measurements"}
      </Button>
    </form>
  );
}

export function NewProfile() {
  const [open, setOpen] = useState(false);
  return open ? (
    <div className="rounded-[var(--radius-lg)] border border-line bg-white/60 p-6">
      <ProfileForm onDone={() => setOpen(false)} />
    </div>
  ) : (
    <Button variant="outline" onClick={() => setOpen(true)}>
      + Add a measurement profile
    </Button>
  );
}
