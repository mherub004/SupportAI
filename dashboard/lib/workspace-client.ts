export function workspaceHeaders() {
  const test = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("workspace") === "test";
  return { "X-SupportFlow-Workspace": test ? "test" : "company" };
}
