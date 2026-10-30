import type { Metadata } from "next";
import "./styles.css";
export const metadata: Metadata = { title: "SupportFlow AI · Operations", description: "Knowledge-grounded email support review" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
