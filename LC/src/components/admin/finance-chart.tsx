"use client";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const fmt = new Intl.NumberFormat("en-PK", { notation: "compact", maximumFractionDigits: 1 });

export function FinanceChart({ data }: { data: { month: string; revenue: number; expenses: number; net_profit: number }[] }) {
  const rows = data.map((d) => ({
    ...d,
    label: new Date(`${d.month}-01T00:00:00`).toLocaleDateString("en-PK", { month: "short" }),
  }));
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} barGap={4} margin={{ left: -12, right: 4, top: 8 }}>
          <CartesianGrid vertical={false} stroke="#e2d5c1" strokeDasharray="3 4" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#6f6468", fontSize: 12 }} />
          <YAxis tickFormatter={(v) => fmt.format(v)} tickLine={false} axisLine={false} tick={{ fill: "#6f6468", fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: "rgba(59,31,43,0.04)" }}
            formatter={(v) => `Rs ${Number(v).toLocaleString("en-PK")}`}
            contentStyle={{ borderRadius: 10, border: "1px solid #d8ccbb", fontSize: 13 }}
          />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" name="Revenue" fill="#3b1f2b" radius={[4, 4, 0, 0]} />
          <Bar dataKey="expenses" name="Expenses" fill="#d9c39a" radius={[4, 4, 0, 0]} />
          <Bar dataKey="net_profit" name="Net profit" fill="#2f6b4f" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
