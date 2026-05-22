"use client";

import { useTheme } from "next-themes";
import { Moon, Sun, Monitor } from "lucide-react";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Hydration safety — bez tego flash złej ikonki przy pierwszym renderze.
  useEffect(() => setMounted(true), []);
  if (!mounted) {
    return (
      <div className="w-full h-9 rounded-md border border-sidebar-border" />
    );
  }

  const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark";
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  const label =
    theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";

  return (
    <button
      onClick={() => setTheme(next)}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-sidebar-accent/60 text-sidebar-foreground/80 transition-colors"
      title={`Click = ${next}`}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span>Theme: {label}</span>
    </button>
  );
}
