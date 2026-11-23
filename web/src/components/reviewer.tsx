"use client";

import { useSyncExternalStore } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const KEY = "bsb.reviewer";


const listeners = new Set<() => void>();
let memory = "";

function read() {
  try {
    return localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory; // storage blocked: keep it for this page only
  }
}

/** Reviewer initials, remembered in this browser. Every approval records them. */
export function useReviewer() {
  const reviewer = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => "",
  );
  const update = (v: string) => {
    memory = v.toUpperCase().slice(0, 8);
    try {
      localStorage.setItem(KEY, memory);
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l());
  };
  return [reviewer, update] as const;
}

export function ReviewerField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="reviewer" className="whitespace-nowrap text-sm text-muted-foreground">
        Your initials
      </Label>
      <Input
        id="reviewer"
        className="w-20 uppercase"
        placeholder="TS"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
