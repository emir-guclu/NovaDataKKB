import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const rawUrl = searchParams.get("url");
  const customName = searchParams.get("name");

  if (!rawUrl) {
    return new NextResponse("Missing url parameter", { status: 400 });
  }

  const cleanName = (customName || "grafik")
    .toLowerCase()
    .replace(/[^a-z0-9ğüşıöç_\-\s]/gi, "")
    .trim()
    .replace(/\s+/g, "_")
    .substring(0, 50) || "analitik_grafik";

  const filename = `${cleanName}.png`;

  // Backend hostlarını dene (127.0.0.1 ve localhost)
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  let targetUrl = rawUrl;
  if (rawUrl.startsWith("/")) {
    targetUrl = `${apiBase}${rawUrl}`;
  }

  const candidateUrls = [
    targetUrl,
    targetUrl.replace("localhost", "127.0.0.1"),
    targetUrl.replace("127.0.0.1", "localhost"),
  ];

  for (const url of candidateUrls) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) {
        const contentType = res.headers.get("content-type") || "image/png";
        const buffer = await res.arrayBuffer();

        return new NextResponse(buffer, {
          status: 200,
          headers: {
            "Content-Type": contentType,
            "Content-Disposition": `attachment; filename="${filename}"`,
            "Cache-Control": "no-cache, no-store, must-revalidate",
          },
        });
      }
    } catch {
      // Bir sonraki adrese geç
      continue;
    }
  }

  return new NextResponse("Görsel sunucudan alınamadı", { status: 404 });
}
