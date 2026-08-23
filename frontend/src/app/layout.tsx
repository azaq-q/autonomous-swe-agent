import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Autonomous SWE Agent",
  description: "AI software engineering assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="border-b border-gray-200 bg-white">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
            <Link href="/" className="font-bold text-gray-900">
              Autonomous SWE Agent
            </Link>
            <Link href="/" className="text-sm text-gray-600 hover:text-gray-900">
              Dashboard
            </Link>
            <Link href="/chat" className="text-sm text-gray-600 hover:text-gray-900">
              Agent Chat
            </Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
