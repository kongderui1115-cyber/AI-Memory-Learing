import { notFound } from "next/navigation";
import DesktopPreview from "@/components/desktop/DesktopPreview";
import {
  navigation,
  previewWorkspace,
} from "@/components/desktop/preview-data";
import type { PreviewView } from "@/components/desktop/preview-data";

export default async function PreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ view: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { view } = await params;
  const allowed = [
    ...navigation.map((item) => item.id),
    "settings",
    "help",
    "admin",
  ];
  if (!allowed.includes(view)) notFound();
  const search = await searchParams;
  const subject = typeof search.subject === "string" ? search.subject : "all";
  const prompt =
    typeof search.prompt === "string"
      ? search.prompt
      : typeof search.action === "string"
        ? `请帮我${search.action}`
        : "";
  return (
    <DesktopPreview
      key={`${view}:${subject}:${prompt}`}
      view={view as PreviewView}
      data={previewWorkspace}
      initialSubject={subject}
      initialPrompt={prompt}
    />
  );
}
