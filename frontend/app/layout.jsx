import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { AppProviders } from '@/components/app-providers';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['cyrillic', 'latin'] });
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['cyrillic', 'latin'] });

export const metadata = {
  title: 'Taskora — O‘zbekiston freelance platformasi',
  description: 'O‘zbekistondagi frilanserlar va buyurtmachilar uchun ishonchli, xavfsiz va qulay platforma.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="uz">
      <body className={`${geistSans.variable} ${geistMono.variable}`}><AppProviders>{children}</AppProviders></body>
    </html>
  );
}
