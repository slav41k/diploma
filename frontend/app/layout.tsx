import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Disinfo Detection Dashboard",
  description: "Прототип ІС виявлення дезінформації та ботнетів",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="uk">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
