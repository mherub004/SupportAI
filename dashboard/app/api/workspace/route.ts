import { NextRequest, NextResponse } from "next/server";
import { sameOrigin } from "../../../lib/origin";
import { isTestWorkspace } from "../../../lib/workspace";

export async function GET(request: NextRequest) {
  return NextResponse.json({ workspace: isTestWorkspace(request) ? "test" : "company", test_available: Boolean(process.env.TEST_API_URL) }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  if (!request.cookies.get("sf_session")) return NextResponse.json({ detail: "Sign in required" }, { status: 401 });
  let input;
  try { input = await request.json(); } catch { return NextResponse.json({ detail: "Invalid workspace" }, { status: 400 }); }
  if (!["company", "test"].includes(input.workspace)) return NextResponse.json({ detail: "Invalid workspace" }, { status: 400 });
  if (input.workspace === "test" && !process.env.TEST_API_URL) return NextResponse.json({ detail: "The personal test backend has not been deployed" }, { status: 409 });
  const response = NextResponse.json({ workspace: input.workspace });
  response.cookies.set("sf_workspace", input.workspace, { httpOnly: true, secure: process.env.COOKIE_SECURE !== "false", sameSite: "strict", path: "/", maxAge: 86400 });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
