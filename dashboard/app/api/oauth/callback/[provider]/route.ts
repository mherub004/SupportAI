import { NextRequest } from "next/server";
import { completeOAuth } from "../../../../../lib/oauth-callback";

export async function GET(request: NextRequest, context: { params: Promise<{ provider: string }> }) {
  return completeOAuth(request, (await context.params).provider);
}
