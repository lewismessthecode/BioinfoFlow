"use client"

import Link from "next/link"
import { ArrowUpRight, Github } from "@/lib/icons"
import { Logo } from "@/components/bioinfoflow/logo"
import { useTranslations } from "next-intl"

export function Footer() {
  const t = useTranslations("landing.footer")
  const primaryLinks = [
    { label: t("product.agent"), href: "#product" },
    { label: t("product.workflows"), href: "#features" },
    { label: t("legal.security"), href: "#security" },
    { label: t("resources.documentation"), href: "#" },
  ]

  return (
    <footer className="landing-footer-shell bg-[var(--landing-cta-bg)] px-5 pb-8 text-[var(--landing-cta-fg)] md:px-8 md:pb-10">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <div>
            <Link href="/" className="inline-flex items-center gap-3">
              <Logo size={30} className="text-[var(--landing-cta-fg)]" />
              <span className="text-sm font-semibold tracking-tight">Bioinfoflow</span>
            </Link>
            <p className="mt-5 max-w-sm text-sm leading-6 opacity-55">
              {t("tagline")}
            </p>
          </div>

          <nav className="flex flex-wrap gap-x-8 gap-y-4 lg:justify-self-end">
            {primaryLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="group inline-flex items-center gap-2 whitespace-nowrap text-sm opacity-55 transition-opacity hover:opacity-100"
              >
                {link.label}
                <ArrowUpRight className="size-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </Link>
            ))}
          </nav>
        </div>

        <div className="mt-16 overflow-hidden border-y border-white/10 py-4" aria-hidden="true">
          <p className="text-[clamp(3.5rem,10.5vw,9rem)] font-medium leading-none tracking-[-0.075em] opacity-[0.08]">
            Bioinfoflow
          </p>
        </div>

        <div className="flex flex-col gap-5 pt-6 text-xs opacity-45 sm:flex-row sm:items-center sm:justify-between">
          <p>{t("copyright", { year: new Date().getFullYear() })}</p>
          <div className="flex items-center gap-6">
            <Link href="#" className="transition-opacity hover:opacity-100">{t("legal.privacy")}</Link>
            <Link href="#" className="transition-opacity hover:opacity-100">{t("legal.terms")}</Link>
            <a
              href="https://github.com/lewismessthecode/BioinfoFlow"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 transition-opacity hover:opacity-100"
            >
              <Github className="size-3.5" />
              GitHub
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
