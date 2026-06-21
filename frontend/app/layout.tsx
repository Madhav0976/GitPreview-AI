import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GitPreview AI',
  description: 'Preview GitHub repositories with a fast AI-powered summary.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
