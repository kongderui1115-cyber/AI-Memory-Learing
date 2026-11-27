import { Suspense } from "react";
import Workspace from "@/components/portal/Workspace";
export default function Page() {
  return (
    <Suspense fallback={<div>正在载入…</div>}>
      <Workspace onboarding />
    </Suspense>
  );
}
