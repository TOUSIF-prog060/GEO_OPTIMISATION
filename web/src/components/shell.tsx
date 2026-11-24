"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useApi } from "@/hooks/use-api";
import type { Status } from "@/lib/api";
import { providerLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type Counts = { counts: Record<string, number> };

// The workflow really is a sequence, so these steps are numbered.
const STEPS = [
  { href: "/discovery", label: "Ask the engines", count: "runs", unit: "runs" },
  { href: "/visibility", label: "Measure visibility", count: "answers", unit: "answers" },
  { href: "/opportunities", label: "Find gaps", count: "opportunities", unit: "gaps" },
  { href: "/copilot", label: "Draft content", count: "drafts", unit: "drafts" },
  { href: "/agent", label: "Run the agent", count: null, unit: "" },
  { href: "/experiments", label: "Re-test", count: "experiments_done", unit: "done" },
] as const;

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const { data } = useApi<Counts>("/overview");
  const { data: status } = useApi<Status>("/status");
  const counts = data?.counts ?? {};

  const item = (href: string, active: boolean) =>
    cn(
      "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
      "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
      active
        ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
        : "text-muted-foreground hover:bg-muted hover:text-foreground",
    );

  return (
    <nav className="flex h-full flex-col gap-6" aria-label="Main">
      <Link href="/" onClick={onNavigate} className="block px-3 pt-1">
        <span className="font-[family-name:var(--font-bricolage)] text-[1.35rem] font-semibold leading-none tracking-tight">
          Beyond the
          <br />
          Search Bar
        </span>
        <span className="mt-2 block text-xs text-muted-foreground">
          {status ? `${status.project.target} in AI answers` : "AI answer visibility"}
        </span>
      </Link>

      <div className="flex flex-col gap-1">
        <Link href="/" onClick={onNavigate} className={item("/", path === "/")}>
          <span className="grid size-6 place-items-center rounded-full border text-[0.7rem]">
            ◎
          </span>
          Overview
        </Link>
      </div>

      <div className="flex flex-col gap-1">
        <p className="px-3 pb-1 text-xs text-muted-foreground">Workflow</p>
        <ol className="relative flex flex-col gap-1">
          <span
            aria-hidden
            className="absolute left-[1.45rem] top-4 bottom-4 w-px bg-border"
          />
          {STEPS.map((s, i) => {
            const active = path.startsWith(s.href);
            const n = s.count ? counts[s.count] : undefined;
            return (
              <li key={s.href} className="relative">
                <Link href={s.href} onClick={onNavigate} className={item(s.href, active)}>
                  <span
                    className={cn(
                      "num relative grid size-6 shrink-0 place-items-center rounded-full border bg-sidebar text-[0.7rem]",
                      active && "border-primary bg-primary text-primary-foreground",
                      !active && n && n > 0 && "border-primary/50 text-primary",
                    )}
                  >
                    {i + 1}
                  </span>
                  <span className="flex-1">{s.label}</span>
                  {n != null && n >= 0 && (
                    <span className="num text-xs text-muted-foreground">{n}</span>
                  )}
                </Link>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="flex flex-col gap-1">
        <Link
          href="/validation"
          onClick={onNavigate}
          className={item("/validation", path.startsWith("/validation"))}
        >
          <span className="grid size-6 place-items-center rounded-full border text-[0.7rem]">
            ✓
          </span>
          Check accuracy
        </Link>
        <Link
          href="/models"
          onClick={onNavigate}
          className={item("/models", path.startsWith("/models"))}
        >
          <span className="grid size-6 place-items-center rounded-full border text-[0.7rem]">
            ƒ
          </span>
          What drives visibility
        </Link>
      </div>

      <div className="mt-auto flex flex-col gap-3 px-3 pb-2">
        {status && (
          <ul className="space-y-1.5 text-xs">
            <li className="flex items-center gap-2">
              <Dot ok={status.db.ok} />
              Database {status.db.ok ? "connected" : "offline"}
            </li>
            {status.providers.map((p) => (
              <li key={p.name} className="flex items-center gap-2">
                <Dot ok={p.has_key} />
                <span>{providerLabel(p.name)}</span>
                <span className="text-muted-foreground">{p.has_key ? p.model : "no key"}</span>
              </li>
            ))}
          </ul>
        )}
        <ThemeToggle />
      </div>
    </nav>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={cn("size-1.5 rounded-full", ok ? "bg-gain" : "bg-muted-foreground/40")}
    />
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 border-r bg-sidebar px-3 py-6 lg:block">
        <Nav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b bg-background/90 px-4 py-3 backdrop-blur lg:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Open menu">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 bg-sidebar px-3 py-6">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <Nav onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <span className="font-[family-name:var(--font-bricolage)] font-semibold">
            Beyond the Search Bar
          </span>
        </header>
        <main className="mx-auto w-full max-w-[1240px] flex-1 px-4 py-8 sm:px-8 lg:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
