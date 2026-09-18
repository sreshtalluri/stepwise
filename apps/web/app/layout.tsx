import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Stepwise Mesh Platform',
  description: 'Full-body multi-person mesh recovery for dance videos.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
