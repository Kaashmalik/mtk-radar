"use client";

/** System → light → dark theme switch. The choice is a per-browser
 * convenience (localStorage); storage failures just fall back to the OS. */

import { useEffect, useState } from "react";

import Icon, { type IconName } from "./Icon";

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_KEY = "mtk-theme";
const ORDER: ThemeChoice[] = ["system", "light", "dark"];
const LABEL: Record<ThemeChoice, string> = {
  system: "Theme: follows system",
  light: "Theme: light",
  dark: "Theme: dark",
};

/** Runs before first paint (inlined in <head>) so there is no theme flash. */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* private mode / blocked storage: the theme still applies for this tab */
  }
}

const ICON: Record<ThemeChoice, IconName> = { system: "monitor", light: "sun", dark: "moon" };

export default function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>("system");

  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    if (current === "light" || current === "dark") setChoice(current);
  }, []);

  function cycle() {
    const next = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
    apply(next);
    setChoice(next);
  }

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={cycle}
      aria-label={`${LABEL[choice]} (click to change)`}
      title={LABEL[choice]}
    >
      {/* keyed so each change remounts the icon and plays its spin-in */}
      <Icon key={choice} name={ICON[choice]} size={16} strokeWidth={1.8} className="icon-swap" />
    </button>
  );
}
