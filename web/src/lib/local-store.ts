"use client";

import { useSyncExternalStore } from "react";

// Small per-browser settings (help strip collapsed, tour seen). Storage can be blocked
// (private windows), so every read and write falls back to memory for this page.
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function read(key: string): string | null {
  try {
    return localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}

export function writeLocal(key: string, value: string | null) {
  if (value == null) memory.delete(key);
  else memory.set(key, value);
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage blocked: memory copy is enough */
  }
  listeners.forEach((l) => l());
}

/** A remembered string; `serverValue` is used before the browser has loaded. */
export function useLocal(key: string, serverValue: string | null = null) {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => read(key),
    () => serverValue,
  );
}

/** Current value of one URL query parameter, kept in sync with history changes. */
const urlListeners = new Set<() => void>();
export function setQuery(name: string, value: string | null) {
  const q = new URLSearchParams(window.location.search);
  if (value == null) q.delete(name);
  else q.set(name, value);
  window.history.replaceState(null, "", q.size ? `?${q}` : window.location.pathname);
  urlListeners.forEach((l) => l());
}

export function useQuery(name: string): string | null {
  return useSyncExternalStore(
    (cb) => {
      urlListeners.add(cb);
      window.addEventListener("popstate", cb);
      return () => {
        urlListeners.delete(cb);
        window.removeEventListener("popstate", cb);
      };
    },
    () => new URLSearchParams(window.location.search).get(name),
    () => null,
  );
}
