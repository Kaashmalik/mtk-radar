export function currentMonth(now = new Date()) {
  // Pakistan Standard Time (UTC+5), so month-end closes on the local calendar
  const pk = new Date(now.getTime() + 5 * 3600 * 1000);
  return pk.toISOString().slice(0, 7);
}

export function splitProfit(net: number, reservePercent: number, sharePercentA = 50) {
  const reserve = net > 0 ? Math.round((net * reservePercent) / 100) : 0;
  const distributable = net - reserve;
  const shareA = Math.round((distributable * sharePercentA) / 100);
  return { reserve, distributable, shareA, shareB: distributable - shareA };
}

export function monthLabel(month: string) {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString("en-PK", { month: "long", year: "numeric" });
}
