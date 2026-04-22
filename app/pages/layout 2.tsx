import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Conference Scheduler",
  description: "Hamilton College conference and symposium scheduling application",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
