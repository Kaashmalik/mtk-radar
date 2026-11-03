import Link from "next/link";
import { getStaff } from "@/lib/auth";
import { getCashClosings, getRiderJobs, getRiders } from "@/lib/data/admin";
import { addRider, assignRider, setRiderActive, verifyCashClosing } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle, Stat } from "@/components/admin/ui";
import { ActionButton, ActionForm, StatusSelect } from "@/components/admin/controls";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { zones } from "@/lib/config";
import { rs } from "@/lib/utils";

export default async function RidersPage() {
  await getStaff();
  const [jobs, riders, closings] = await Promise.all([getRiderJobs(), getRiders(), getCashClosings()]);
  const byZone = zones.map((z) => ({ zone: z, jobs: jobs.filter((j) => j.order?.zone_code === z.code) }));
  const cash = jobs.reduce((s, j) => s + j.cash_to_collect, 0);
  const riderOptions = [{ value: "", label: "Unassigned" }, ...riders.filter((r) => r.is_active).map((r) => ({ value: r.id, label: r.full_name }))];

  return (
    <>
      <PageTitle title="Dispatch & riders" sub="Open pickups, deliveries and home measurement visits, grouped by zone. Riders see their jobs in the rider app at /rider." />
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <Stat label="Pickups" value={String(jobs.filter((j) => j.type === "pickup").length)} />
        <Stat label="Deliveries" value={String(jobs.filter((j) => j.type === "delivery").length)} />
        <Stat label="Unassigned" value={String(jobs.filter((j) => !j.rider_id).length)} tone={jobs.some((j) => !j.rider_id) ? "warn" : "default"} />
        <Stat label="Cash to collect" value={rs(cash)} hint="Reconcile at shift end" />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        {byZone.map(({ zone, jobs }) => (
          <Panel key={zone.code} title={`Zone ${zone.code} · ${zone.name} (${jobs.length})`}>
            {jobs.length === 0 ? (
              <Empty>No jobs</Empty>
            ) : (
              <ul className="space-y-3">
                {jobs.map((j) => (
                  <li key={j.id} className="rounded-[var(--radius-md)] border border-line p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold capitalize">
                        {j.type.replace("_", " ")} · {j.order?.order_no}
                      </span>
                      <Badge value={j.status} />
                    </div>
                    <p className="mt-1">{j.order?.customer?.full_name}</p>
                    <p className="text-xs text-muted">
                      {j.order?.customer?.area} · {j.order?.customer?.address}
                    </p>
                    {j.notes && <p className="mt-1 text-xs text-wine">{j.notes}</p>}
                    <p className="mt-2 text-xs">
                      {j.scheduled_date} · {j.slot}
                      {j.cash_to_collect > 0 && <span className="ml-2 font-semibold text-wine">Collect {rs(j.cash_to_collect)}</span>}
                    </p>
                    <div className="mt-2">
                      <StatusSelect value={j.rider_id ?? ""} options={riderOptions} onChange={assignRider.bind(null, j.id)} success="Rider assigned" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <Panel title={`Riders (${riders.length})`}>
            <ul className="divide-y divide-line">
              {riders.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <div>
                    <p className="font-semibold">
                      {r.full_name} {!r.is_active && <Badge value="inactive" />}
                    </p>
                    <p className="text-xs text-muted">
                      {r.phone} · {r.bike_no ?? "no bike no."} · Zones {r.zones.join(", ") || "—"} · {r.profile_id ? "App login ✓" : "No app login"}
                    </p>
                  </div>
                  <ActionButton action={setRiderActive.bind(null, r.id, !r.is_active)} success={r.is_active ? "Rider deactivated" : "Rider activated"} variant="outline">
                    {r.is_active ? "Deactivate" : "Activate"}
                  </ActionButton>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Cash closings">
            {closings.length === 0 ? (
              <Empty>No closings submitted yet.</Empty>
            ) : (
              <ul className="divide-y divide-line text-sm">
                {closings.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                    <span>
                      {c.closing_date} · {c.rider?.full_name}
                    </span>
                    <span className="flex items-center gap-3">
                      Expected {rs(c.expected)} · Deposited {rs(c.deposited)}
                      <span className={c.difference === 0 ? "text-success" : "font-semibold text-danger"}>{c.difference === 0 ? "✓ matched" : rs(c.difference)}</span>
                      <ActionButton action={verifyCashClosing.bind(null, c.id)} success="Closing verified" variant="ghost">
                        Verify
                      </ActionButton>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="Add rider">
          <ActionForm action={addRider} success="Rider added" className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="fullName">Name</Label>
                <Input id="fullName" name="fullName" required />
              </div>
              <div>
                <Label htmlFor="phone">Phone</Label>
                <Input id="phone" name="phone" required inputMode="tel" />
              </div>
              <div>
                <Label htmlFor="cnic">CNIC</Label>
                <Input id="cnic" name="cnic" placeholder="35202-xxxxxxx-x" />
              </div>
              <div>
                <Label htmlFor="bikeNo">Bike number</Label>
                <Input id="bikeNo" name="bikeNo" />
              </div>
            </div>
            <fieldset>
              <legend className="mb-1.5 text-sm font-medium">Zones</legend>
              <div className="flex gap-4 text-sm">
                {zones.map((z) => (
                  <label key={z.code} className="flex items-center gap-1.5">
                    <input type="checkbox" name="zones" value={z.code} defaultChecked={z.code !== "C"} className="accent-[var(--color-plum)]" /> {z.code} · {z.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="rounded-[var(--radius-md)] bg-cream/70 p-4">
              <p className="text-sm font-medium">Rider app login (optional)</p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Input name="email" type="email" placeholder="Email" />
                <Input name="password" type="text" placeholder="Temporary password" />
              </div>
              <p className="mt-2 text-xs text-muted">
                The rider signs in at <Link href="/rider" className="underline">laraibcreative.com/rider</Link>.
              </p>
            </div>
            <Button type="submit">Add rider</Button>
          </ActionForm>
        </Panel>
      </div>
    </>
  );
}
