import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { sameOrigin } from "../../../../../lib/origin";

export async function POST(request: NextRequest, context: { params: Promise<{ provider: string }> }) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const { provider } = await context.params;
  if (!["google", "salesforce", "netsuite"].includes(provider)) return NextResponse.json({ detail: "Unsupported provider" }, { status: 404 });
  const token = request.cookies.get("sf_session")?.value;
  if (!token) return NextResponse.json({ detail: "Sign in first" }, { status: 401 });
  const binding = randomBytes(32).toString("base64url");
  try {
    const input = await request.json();
    const result = await fetch(`${process.env.API_URL || "http://127.0.0.1:8000"}/api/business/oauth/${provider}/start`, {
      method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ binding, personal: input.personal === true }), cache: "no-store", signal: AbortSignal.timeout(30000),
    });
    const data = await result.json();
    const response = NextResponse.json(data, { status: result.status, headers: { "Cache-Control": "no-store" } });
    if (result.ok) response.cookies.set(`sf_oauth_${provider}`, binding, { httpOnly: true, sameSite: "lax",
      secure: process.env.COOKIE_SECURE !== "false", path: `/api/oauth/callback/${provider}`, maxAge: 600 });
    return response;
  } catch { return NextResponse.json({ detail: "Authorization service unavailable" }, { status: 503 }); }
}
