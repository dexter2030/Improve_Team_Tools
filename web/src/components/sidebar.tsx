"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Users,
  UserPlus,
  Swords,
  Database,
  LineChart,
  Trophy,
  Settings,
  LogOut,
  Home,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/", label: "Home", icon: Home },
  { href: "/scouting", label: "Scouting List", icon: Users },
  { href: "/scouting/add", label: "Add Player", icon: UserPlus },
  { href: "/draft-analyzer", label: "Draft Analyzer", icon: Swords },
  { href: "/database", label: "Database", icon: Database },
  { href: "/players-data", label: "Players Data", icon: LineChart },
  { href: "/match-data", label: "Match Data", icon: Trophy },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground flex flex-col">
      <div className="px-6 py-5 border-b border-sidebar-border">
        <h1 className="text-lg font-semibold tracking-tight">
          Improve Team Tools
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          LoL Scouting Dashboard
        </p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href ||
            (href !== "/" && href !== "/scouting" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "hover:bg-sidebar-accent/60 text-sidebar-foreground/80"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-3 py-3 border-t border-sidebar-border space-y-1">
        <ThemeToggle />
        <form action="/api/auth/logout" method="post">
          <button
            type="submit"
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-sidebar-accent/60 text-sidebar-foreground/80 transition-colors"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span>Wyloguj</span>
          </button>
        </form>
        <p className="px-3 pt-1 text-[10px] text-muted-foreground">
          Live data — Riot API &amp; Leaguepedia
        </p>
      </div>
    </aside>
  );
}
