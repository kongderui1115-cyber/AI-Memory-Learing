import PushReadingPreview from "@/components/desktop/PushReadingPreview";
import { previewWorkspace } from "@/components/desktop/preview-data";

export default function PushPreviewPage() {
  return <PushReadingPreview data={previewWorkspace} />;
}
