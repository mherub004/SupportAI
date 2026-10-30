import fs from "node:fs";

const config = JSON.parse(fs.readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8"));
try {
  const backend = new URL(config.vars.API_URL);
  if (backend.protocol !== "https:" || backend.username || backend.password ||
      backend.hostname.endsWith(".invalid") || ["localhost", "127.0.0.1"].includes(backend.hostname) ||
      backend.pathname !== "/" || backend.search || backend.hash) {
    throw new Error("Invalid backend URL");
  }
} catch {
  console.error("Deployment blocked: set vars.API_URL in wrangler.jsonc to your real HTTPS backend origin. The Python API, worker and PostgreSQL must be hosted separately. Never put credentials in this URL.");
  process.exit(1);
}
console.log("Backend URL configured. Confirm OPERATOR_TOKEN is stored as a Cloudflare Worker secret and matches the backend before deploying.");
