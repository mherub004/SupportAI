export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const backend = process.env.API_URL;
    if (!backend) return Response.json({ status: "unconfigured" }, { status: 503 });
    const backends = [backend, process.env.TEST_API_URL].filter((url): url is string => Boolean(url));
    const results = await Promise.all(backends.map(url => fetch(`${url.replace(/\/$/, "")}/health`, {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    })));
    if (results.some(response => !response.ok)) throw new Error("Backend unavailable");
    return Response.json({ status: "ok" });
  } catch {
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
