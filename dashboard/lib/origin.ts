import { NextRequest } from "next/server";

export function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  const configured = process.env.DASHBOARD_ORIGIN;
  return Boolean(origin && origin === (configured || request.nextUrl.origin));
}
