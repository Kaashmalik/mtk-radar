import { Suspense } from "react";
import { connection } from "next/server";
import { LogOut } from "lucide-react";
import { getRider } from "@/lib/auth";
import { getJobsForRider } from "@/lib/data/rider";
import { signOut } from "@/lib/actions/admin";
import { submitCashClosing } from "@/lib/actions/rider";
import { JobCard } from "@/components/rider/job-card";
import { ActionForm } from "@/components/admin/controls";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { rs } from "@/lib/utils";

function today() {
  return new Date(Date.now() + 5 * 3600 * 1000).toISOString().slice(0, 10);
}

async function RiderHome() {
  await connection();
  const rider = await getRider();
  const date = today();
  const jobs = await getJobsForRider(rider.riderId, date);
  const open = jobs.filter((j) => !["done", "failed"].includes(j.status));
  const closed = jobs.filter((j) => ["done", "failed"].includes(j.status));
  const cashCollected = closed.reduce((s, j) => s + j.cash_collected, 0);
  const cashPending = open.reduce((s, j) => s + j.cash_to_collect, 0);

  return (
    <>
      <header className="sticky top-0 z-20 bg-plum px-4 pt-4 pb-5 text-ivory">
        <div className="flex items-center justify-between">
          <Logo light />
          <form action={signOut}>
            <button className="grid size-10 place-items-center rounded-full bg-ivory/10" aria-label="Sign out">
              <LogOut className="size-4" />
            </button>
          </form>
        </div>
        <p className="font-display mt-5 text-2xl">Salam, {rider.name.split(" ")[0]}</p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-[var(--radius-md)] bg-ivory/10 py-2">
            <p className="font-display text-xl">{open.length}</p>
            Open jobs
          </div>
          <div className="rounded-[var(--radius-md)] bg-ivory/10 py-2">
            <p className="font-display text-xl">{closed.filter((j) => j.status === "done").length}</p>
            Done today
          </div>
          <div className="rounded-[var(--radius-md)] bg-ivory/10 py-2">
            <p className="font-display text-xl">{rs(cashCollected)}</p>
            Cash with you
          </div>
        </div>
        {rider.preview && <p className="mt-3 rounded bg-gold/20 px-2 py-1 text-xs text-gold-soft">Preview mode — sample jobs, buttons won&rsquo;t save.</p>}
      </header>

      <main className="mx-auto max-w-lg space-y-4 p-4 pb-16">
        {open.length === 0 && <p className="py-10 text-center text-muted">No open jobs. 🎉</p>}
        {open.map((j) => (
          <JobCard key={j.id} job={j} />
        ))}
        {cashPending > 0 && <p className="text-center text-xs text-muted">Still to collect on open jobs: {rs(cashPending)}</p>}

        {closed.length > 0 && (
          <>
            <h2 className="pt-4 font-sans text-sm font-semibold tracking-normal text-muted">Finished today</h2>
            {closed.map((j) => (
              <JobCard key={j.id} job={j} />
            ))}
          </>
        )}

        <section className="rounded-[var(--radius-lg)] border border-line bg-white p-4">
          <h2 className="font-sans text-sm font-semibold tracking-normal">End of shift — hand over cash</h2>
          <p className="mt-1 text-xs text-muted">Collected today: {rs(cashCollected)}. Enter what you are handing to the office.</p>
          <ActionForm action={submitCashClosing} success="Cash closing submitted" className="mt-3 flex gap-2">
            <input type="hidden" name="date" value={date} />
            <Input name="deposited" type="number" min={0} defaultValue={cashCollected} required />
            <Button type="submit">Submit</Button>
          </ActionForm>
        </section>
      </main>
    </>
  );
}

export default function RiderPage() {
  return (
    <Suspense fallback={<div className="h-40 animate-pulse bg-plum" />}>
      <RiderHome />
    </Suspense>
  );
}
