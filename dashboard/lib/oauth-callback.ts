import { NextRequest, NextResponse } from "next/server";

export async function completeOAuth(request: NextRequest, provider: string, test = false) {
  const segment = test ? "test/" : "";
  const cookie = `sf_oauth_${test ? "test_" : ""}${provider}`;
  const backend = test ? process.env.TEST_API_URL : (process.env.API_URL || "http://127.0.0.1:8000");
  const origin = process.env.DASHBOARD_ORIGIN || request.nextUrl.origin;
  if (!["google", "salesforce", "netsuite"].includes(provider)) return new NextResponse("Unsupported provider", { status: 404 });
  let connected = false;
  const binding = request.cookies.get(cookie)?.value;
  const state = request.nextUrl.searchParams.get("state");
  const code = request.nextUrl.searchParams.get("code");
  const token = process.env.OPERATOR_TOKEN;
  if (backend && binding && state && code && state.length <= 200 && code.length <= 4000 && token && !request.nextUrl.searchParams.has("error")) {
    try {
      const response = await fetch(`${backend}/api/business/oauth/${provider}/complete`, {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ binding, state, code }), cache: "no-store", signal: AbortSignal.timeout(60000),
      });
      connected = response.ok;
    } catch { /* OAuth codes are not retried after uncertain outcomes. */ }
  }
  const response = NextResponse.redirect(new URL(`/?workspace=${test ? "test" : "company"}&connection=${provider}&result=${connected ? "connected" : "failed"}`, origin));
  response.cookies.set(cookie, "", { httpOnly: true, sameSite: "lax", path: `/api/oauth/callback/${segment}${provider}`, maxAge: 0,
    secure: process.env.COOKIE_SECURE !== "false" });
  if (binding) response.cookies.set("sf_workspace", test ? "test" : "company", { httpOnly: true, sameSite: "strict", secure: process.env.COOKIE_SECURE !== "false", path: "/", maxAge: 86400 });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
