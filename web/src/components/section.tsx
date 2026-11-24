"use client";

import { createContext, useContext } from "react";

import { HowItWorks, type HelpStep } from "@/components/help";
import { setQuery, useQuery } from "@/lib/local-store";
import { cn } from "@/lib/utils";

/** True inside a section: page views then show a compact header instead of a page title. */
export const Embedded = createContext(false);
export const useEmbedded = () => useContext(Embedded);

export type SectionTab = {
  id: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  content: React.ReactNode;
};

export function Section({
  step,
  title,
  lede,
  help,
  tabs,
  children,
}: {
  step?: number;
  title: string;
  lede: string;
  help: { id: string; steps: HelpStep[] };
  tabs?: SectionTab[];
  children?: React.ReactNode;
}) {
  const requested = useQuery("tab");
  const active = tabs?.find((t) => t.id === requested) ?? tabs?.[0];

  return (
    <div className="space-y-7">
      <header className="rise-in max-w-3xl">
        {step != null && (
          <p className="mb-2 text-sm font-medium text-primary">Step {step} of 4</p>
        )}
        <h1 className="text-3xl font-semibold sm:text-[2.4rem] sm:leading-[1.05]">{title}</h1>
        <p className="mt-3 text-[1rem] leading-relaxed text-muted-foreground">{lede}</p>
      </header>

      <div className="rise-in" style={{ animationDelay: "80ms" }}>
        <HowItWorks id={help.id} steps={help.steps} />
      </div>

      {tabs && tabs.length > 1 && (
        <div
          role="tablist"
          aria-label={`${title} sections`}
          className="rise-in grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          style={{ animationDelay: "140ms" }}
        >
          {tabs.map((t) => {
            const on = t.id === active?.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setQuery("tab", t.id === tabs[0].id ? null : t.id)}
                className={cn(
                  "group flex items-start gap-3 rounded-xl border p-4 text-left transition-all",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  on
                    ? "border-primary bg-accent shadow-[0_0_0_1px_var(--primary)]"
                    : "bg-card hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm",
                )}
              >
                <span
                  className={cn(
                    "grid size-9 shrink-0 place-items-center rounded-lg transition-colors",
                    on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-hover:text-primary",
                  )}
                >
                  <t.icon className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className={cn("block font-semibold", on && "text-accent-foreground")}>{t.label}</span>
                  <span className="mt-0.5 block text-[0.82rem] leading-snug text-muted-foreground">
                    {t.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      <Embedded.Provider value={true}>
        <div key={active?.id} className="rise-in" role={tabs ? "tabpanel" : undefined}>
          {active?.content ?? children}
        </div>
      </Embedded.Provider>
    </div>
  );
}
