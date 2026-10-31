import { NextRequest } from "next/server";

export function isTestWorkspace(request: NextRequest) {
  const explicit = request.headers.get("x-supportflow-workspace");
  if (explicit === "test" || explicit === "company") return explicit === "test";
  return request.cookies.get("sf_workspace")?.value === "test";
}

export function backendFor(request: NextRequest) {
  return isTestWorkspace(request) ? process.env.TEST_API_URL : (process.env.API_URL || "http://127.0.0.1:8000");
}
