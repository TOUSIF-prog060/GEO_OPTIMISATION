"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Compass, House, Menu, MessagesSquare, ShieldCheck, Wrench } from "lucide-react";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { startTour, Tour } from "@/components/tour";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useApi } from "@/hooks/use-api";
import type { Status } from "@/lib/api";
import { providerLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

// Four steps, in the order a person actually uses them.
export const STEPS = [
  { href: "/ask", tour: "nav-ask", icon: MessagesSquare, label: "Ask AI", note: "Send questions to the AI engines" },
  { href: "/results", tour: "nav-results", icon: BarChart3, label: "See results", note: "How often each brand is named" },
  { href: "/fix", tour: "nav-fix", icon: Wrench, label: "Fix gaps", note: "Find problems and draft fixes" },
  { href: "/check", tour: "nav-check", icon: ShieldCheck, label: "Check it worked", note: "Re-test and check accuracy" },
] as const;

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const { data: status } = useApi<Status>("/status");
  const engines = status?.providers ?? [];
  const live = engines.filter((p) => p.has_key);

  const item = (active: boolean) =>
    cn(
      "group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
      "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
      active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-muted",
    );
  const icon = (active: boolean) =>
    cn(
      "grid size-8 shrink-0 place-items-center rounded-lg transition-colors",
      active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-hover:text-primary",
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

      <Link href="/" onClick={onNavigate} className={item(path === "/")} data-tour="nav-home">
        <span className={icon(path === "/")}>
          <House className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium">Home</span>
          <span className="block text-xs text-muted-foreground">Summary and your next step</span>
        </span>
      </Link>

      <div>
        <p className="px-3 pb-2 text-xs font-medium text-muted-foreground">Four steps</p>
        <ol className="relative flex flex-col gap-1">
          <span aria-hidden className="absolute top-6 bottom-6 left-[1.75rem] w-px bg-border" />
          {STEPS.map((s, i) => {
            const active = path.startsWith(s.href);
            return (
              <li key={s.href} className="relative">
                <Link href={s.href} onClick={onNavigate} className={item(active)} data-tour={s.tour}>
                  <span className={cn(icon(active), "relative bg-sidebar", active && "bg-primary")}>
                    <s.icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">
                      <span className="num text-muted-foreground">{i + 1}.</span> {s.label}
                    </span>
                    <span className="block text-xs text-muted-foreground">{s.note}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="mt-auto flex flex-col gap-4 px-1 pb-2">
        <Button
          variant="outline"
          className="h-9 justify-start"
          onClick={() => {
            onNavigate?.();
            startTour();
          }}
          data-tour="tour-button"
          hint="A one-minute walkthrough of the app. You can stop it at any time."
        >
          <Compass /> Show me around
        </Button>

        <div data-tour="help-legend" className="space-y-1.5 rounded-lg bg-muted/60 px-3 py-2.5 text-xs text-muted-foreground">
          <p className="flex items-center gap-2">
            <span className="grid size-4 place-items-center rounded-full border text-[0.6rem] font-semibold">?</span>
            Click for a plain explanation
          </p>
          <p>Hover any button to see what it does.</p>
        </div>

        {status && (
          <details className="group px-2 text-xs">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-muted-foreground hover:text-foreground">
              <span className={cn("size-2 rounded-full", status.db.ok ? "bg-gain" : "bg-loss")} />
              {status.db.ok ? "Connected" : "Database offline"} · {live.length} of {engines.length} AI engines
              <span className="ml-auto group-open:rotate-180">⌄</span>
            </summary>
            <ul className="mt-2 space-y-1.5 pl-1">
              <li className="flex items-center gap-2">
                <Dot ok={status.db.ok} /> Database {status.db.ok ? "connected" : "offline"}
              </li>
              {engines.map((p) => (
                <li key={p.name} className="flex items-center gap-2">
                  <Dot ok={p.has_key} />
                  <span>{providerLabel(p.name)}</span>
                  <span className="text-muted-foreground">{p.has_key ? "ready" : "no key yet"}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        <ThemeToggle />
      </div>
    </nav>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return <span aria-hidden className={cn("size-1.5 rounded-full", ok ? "bg-gain" : "bg-muted-foreground/40")} />;
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-72 shrink-0 overflow-y-auto border-r bg-sidebar px-3 py-6 lg:block">
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
            <SheetContent side="left" className="w-80 overflow-y-auto bg-sidebar px-3 py-6">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <Nav onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <span className="font-[family-name:var(--font-bricolage)] font-semibold">Beyond the Search Bar</span>
          <Button variant="ghost" size="icon" className="ml-auto" aria-label="Show me around" onClick={startTour}>
            <Compass />
          </Button>
        </header>
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 py-8 sm:px-8 lg:py-10">{children}</main>
      </div>
      <Tour />
    </div>
  );
}
