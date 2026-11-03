import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const pkr = new Intl.NumberFormat("en-PK", { maximumFractionDigits: 0 });

export function rs(amount: number) {
  // "−Rs 1,200" for losses; -0 renders as "Rs 0"
  return `${amount < 0 ? "−" : ""}Rs ${pkr.format(Math.abs(amount))}`;
}
