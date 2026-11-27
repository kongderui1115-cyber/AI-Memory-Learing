"use client";
import { createContext, useContext, useEffect, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Check } from "lucide-react";
import { initialAdminDemo } from "./admin-console-data";
import type { AdminDemoState } from "./admin-console-data";

const Context = createContext<{
  state: AdminDemoState;
  setState: Dispatch<SetStateAction<AdminDemoState>>;
  notify: (message: string) => void;
} | null>(null);
const key = "memory-os-admin-demo-v1";
export function AdminDemoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(initialAdminDemo);
  const [ready, setReady] = useState(false);
  const [message, notify] = useState("");
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(key) ?? "null");
      if (
        saved &&
        Array.isArray(saved.models) &&
        Array.isArray(saved.sources) &&
        Array.isArray(saved.channels) &&
        Array.isArray(saved.securityEvents)
      )
        setState({ ...initialAdminDemo, ...saved });
    } catch {
      /* The demo also works without browser storage. */
    }
    setReady(true);
  }, []);
  useEffect(() => {
    if (ready)
      try {
        localStorage.setItem(key, JSON.stringify(state));
      } catch {
        /* Optional UI persistence. */
      }
  }, [state, ready]);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => notify(""), 5000);
    return () => clearTimeout(timer);
  }, [message]);
  return (
    <Context.Provider value={{ state, setState, notify }}>
      {ready ? (
        children
      ) : (
        <div className="ac-boot" role="status">
          正在载入管理界面…
        </div>
      )}
      {message && (
        <div className="ds-toast" role="status">
          <Check size={17} />
          {message}
        </div>
      )}
    </Context.Provider>
  );
}
export function useAdminDemo() {
  const context = useContext(Context);
  if (!context) throw new Error("AdminDemoProvider required");
  return context;
}
