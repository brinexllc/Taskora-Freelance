import { Inter, Geist_Mono } from 'next/font/google';
import './globals.css';
import './figma.css';
import './design-system.css';
import { AppProviders } from '@/components/app-providers';

const geistSans = Inter({
  variable: '--font-geist-sans',
  subsets: ['cyrillic', 'latin'],
});
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['cyrillic', 'latin'],
});

export const metadata = {
  title: 'Taskora — IT-заказы и фрилансеры Узбекистана',
  description:
    'O‘zbekistondagi frilanserlar va buyurtmachilar uchun ishonchli, xavfsiz va qulay platforma.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
