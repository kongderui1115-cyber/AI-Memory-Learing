import { BrainCircuit } from "lucide-react";

export function Brand() {
  return (
    <div className="admin-brand">
      <span className="admin-brand-mark"><BrainCircuit size={22} strokeWidth={1.7} aria-hidden="true" /></span>
      <span><strong>AI Learning Memory OS</strong><small>ADMIN CONSOLE</small></span>
    </div>
  );
}
