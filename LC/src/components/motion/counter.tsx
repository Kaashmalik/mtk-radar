"use client";
import { useEffect } from "react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";

const fmt = new Intl.NumberFormat("en-PK");

/** Animates between number values — used for the live order price. */
export function AnimatedNumber({ value, prefix = "" }: { value: number; prefix?: string }) {
  const mv = useMotionValue(value);
  const text = useTransform(mv, (v) => `${prefix}${fmt.format(Math.round(v))}`);
  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.6, ease: [0.22, 1, 0.36, 1] });
    return () => controls.stop();
  }, [mv, value]);
  return <motion.span className="tabular-nums">{text}</motion.span>;
}
