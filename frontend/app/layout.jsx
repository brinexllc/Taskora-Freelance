import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['cyrillic', 'latin'] });
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['cyrillic', 'latin'] });

export const metadata = {
  title: 'Taskora — проекты для талантливых специалистов',
  description: 'Платформа для поиска фриланс-проектов и сильных специалистов.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
