import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, context: { params: Promise<{ provider: string }> }) {
  const { provider } = await context.params;
  const origin = process.env.DASHBOARD_ORIGIN || request.nextUrl.origin;
  if (!["google", "salesforce", "netsuite"].includes(provider)) return new NextResponse("Unsupported provider", { status: 404 });
  let connected = false;
  const binding = request.cookies.get(`sf_oauth_${provider}`)?.value;
  const state = request.nextUrl.searchParams.get("state");
  const code = request.nextUrl.searchParams.get("code");
  const token = process.env.OPERATOR_TOKEN;
  if (binding && state && code && state.length <= 200 && code.length <= 4000 && token && !request.nextUrl.searchParams.has("error")) {
    try {
      const response = await fetch(`${process.env.API_URL || "http://127.0.0.1:8000"}/api/business/oauth/${provider}/complete`, {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ binding, state, code }), cache: "no-store", signal: AbortSignal.timeout(60000),
      });
      connected = response.ok;
    } catch { /* OAuth codes are not retried after uncertain outcomes. */ }
  }
  const response = NextResponse.redirect(new URL(`/?connection=${provider}&result=${connected ? "connected" : "failed"}`, origin));
  response.cookies.set(`sf_oauth_${provider}`, "", { httpOnly: true, sameSite: "lax", path: `/api/oauth/callback/${provider}`, maxAge: 0,
    secure: process.env.COOKIE_SECURE !== "false" });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
