import DesktopPreview from "@/components/desktop/DesktopPreview";
import { previewWorkspace } from "@/components/desktop/preview-data";

export default function PreviewHome() {
  return <DesktopPreview view="dashboard" data={previewWorkspace} />;
}
