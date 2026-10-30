import { NextRequest, NextResponse } from "next/server";
import { sameOrigin } from "../../../../lib/origin";

type Context = { params: Promise<{ path: string[] }> };
async function proxy(request: NextRequest, context: Context) {
  if (!["GET", "HEAD"].includes(request.method) && !sameOrigin(request)) {
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  }
  const token = request.cookies.get("sf_session")?.value;
  if (!token) return NextResponse.json({ detail: "Sign in required" }, { status: 401 });
  const { path } = await context.params;
  if (path.some(p => !/^[a-zA-Z0-9_:@.\-]+$/.test(p))) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }
  const target = `${process.env.API_URL || "http://127.0.0.1:8000"}/api/${path.map(encodeURIComponent).join("/")}`;
  try {
    const response = await fetch(target, { method: request.method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      cache: "no-store", signal: AbortSignal.timeout(120000) });
    return new NextResponse(await response.text(), { status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Backend unavailable" }, { status: 503 });
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
