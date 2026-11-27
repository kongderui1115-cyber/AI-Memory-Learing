import { notFound } from "next/navigation";
import { AdminShell } from "@/components/admin-shell";
import { navigation } from "@/lib/routes";

export default async function ConsolePage({ params }: { params: Promise<{ section?: string[] }> }) {
  const { section = [] } = await params;
  const [first, second] = section;
  const demo = first === "demo";
  if (section.length > (demo ? 2 : 1)) notFound();

  const selected = navigation.find((item) => item.id === ((demo ? second : first) ?? "dashboard"));
  if (!selected) notFound();

  return <AdminShell mode={demo ? "demo" : "live"} section={selected.id} />;
}
