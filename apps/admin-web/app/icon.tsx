import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 32, height: 32, borderRadius: 9, background: "#172649" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 23, height: 23, border: "2px solid #879efe", borderRadius: 18 }}>
        <div style={{ width: 10, height: 10, borderRadius: 8, background: "#6bd6fc" }} />
      </div>
    </div>,
    size,
  );
}
