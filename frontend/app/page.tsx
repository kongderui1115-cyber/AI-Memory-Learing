import { Suspense } from "react";
import Welcome from "@/components/portal/Welcome";

export default function Page() {
  return (
    <Suspense fallback={<div>正在载入…</div>}>
      <Welcome />
    </Suspense>
  );
}
