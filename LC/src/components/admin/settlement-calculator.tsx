"use client";
import { useState } from "react";
import { closeMonth } from "@/lib/actions/admin";
import { splitProfit } from "@/lib/finance";
import { ActionButton } from "./controls";
import { AnimatedNumber } from "@/components/motion/counter";
import { rs } from "@/lib/utils";

type Props = {
  month: string;
  revenue: number;
  expenses: number;
  partnerA: { name: string; drawings: number };
  partnerB: { name: string; drawings: number };
  status: "open" | "draft" | "closed";
  initialReserve: number;
};

export function SettlementCalculator({ month, revenue, expenses, partnerA, partnerB, status, initialReserve }: Props) {
  const [reserve, setReserve] = useState(initialReserve);
  const net = revenue - expenses;
  const split = splitProfit(net, reserve);
  const rows = [
    { label: "Revenue (verified payments)", value: revenue },
    { label: "− Approved expenses", value: -expenses },
    { label: "= Net profit", value: net, strong: true },
    { label: `− Business reserve (${reserve}%)`, value: -split.reserve },
    { label: "= Distributable", value: split.distributable, strong: true },
  ];

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr]">
      <div>
        <ul className="space-y-2 text-sm">
          {rows.map((r) => (
            <li key={r.label} className={`flex justify-between ${r.strong ? "border-t border-line pt-2 font-semibold" : "text-muted"}`}>
              <span>{r.label}</span>
              <span className={`tabular-nums ${r.strong ? (r.value >= 0 ? "text-success" : "text-danger") : ""}`}>{rs(r.value)}</span>
            </li>
          ))}
        </ul>
        <label className="mt-6 block text-sm">
          <span className="flex justify-between">
            <span>Reserve for machines, Eid stock & emergencies</span>
            <span className="font-semibold">{reserve}%</span>
          </span>
          <input
            type="range"
            min={0}
            max={30}
            step={5}
            value={reserve}
            disabled={status !== "open"}
            onChange={(e) => setReserve(Number(e.target.value))}
            className="mt-2 w-full accent-[var(--color-plum)]"
          />
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {[
          { p: partnerA, share: split.shareA },
          { p: partnerB, share: split.shareB },
        ].map(({ p, share }) => (
          <div key={p.name} className="rounded-[var(--radius-lg)] bg-plum p-5 text-ivory">
            <p className="text-xs tracking-wider text-ivory/60 uppercase">{p.name} · 50%</p>
            <p className="font-display mt-2 text-3xl">
              <AnimatedNumber value={share} prefix="Rs " />
            </p>
            <div className="mt-4 space-y-1 border-t border-ivory/15 pt-3 text-xs text-ivory/70">
              <p className="flex justify-between">
                <span>Drawings this month</span>
                <span>−{rs(p.drawings)}</span>
              </p>
              <p className="flex justify-between font-semibold text-ivory">
                <span>{share - p.drawings >= 0 ? "Payable to partner" : "Partner owes business"}</span>
                <span>{rs(Math.abs(share - p.drawings))}</span>
              </p>
            </div>
          </div>
        ))}
        <div className="sm:col-span-2">
          {status === "closed" ? (
            <p className="text-sm text-success">✓ Month closed and approved by both partners.</p>
          ) : (
            <ActionButton
              action={closeMonth.bind(null, month, reserve)}
              success={status === "draft" ? "Your approval is recorded" : "Settlement created — waiting for the other partner"}
              confirm="Lock this month's numbers and record your approval?"
              className="w-full"
            >
              {status === "draft" ? "Approve settlement" : "Close month & approve"}
            </ActionButton>
          )}
          {net < 0 && <p className="mt-2 text-xs text-muted">This month is a loss — it is shared 50/50 as per the partnership deed (or carried forward if you agreed that).</p>}
        </div>
      </div>
    </div>
  );
}
