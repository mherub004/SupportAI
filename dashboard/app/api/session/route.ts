import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { sameOrigin } from "../../../lib/origin";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const { token } = await request.json();
  const expected = process.env.OPERATOR_TOKEN || "";
  if (typeof token !== "string" || expected.length < 32 || token.length > 1024 ||
      Buffer.byteLength(token) !== Buffer.byteLength(expected) ||
      !timingSafeEqual(Buffer.from(token), Buffer.from(expected))) {
    return NextResponse.json({ detail: "Invalid operator token" }, { status: 401 });
  }
  const response = NextResponse.json({ status: "authenticated" });
  response.cookies.set("sf_session", token, { httpOnly: true, secure: process.env.COOKIE_SECURE !== "false",
    sameSite: "strict", path: "/", maxAge: 3600 });
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const response = NextResponse.json({ status: "signed_out" });
  response.cookies.delete("sf_session");
  return response;
}
