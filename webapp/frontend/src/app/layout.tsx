import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Dutch Video Dashboard",
  description: "Manage Dutch language video generation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <Nav />
        <main className="flex-1 container mx-auto px-4 py-6 max-w-7xl">{children}</main>
      </body>
    </html>
  );
}
