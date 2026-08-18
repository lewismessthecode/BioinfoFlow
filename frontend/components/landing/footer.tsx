"use client"

import Link from "next/link"
import { ArrowUpRight, Github } from "@/lib/icons"
import { Logo } from "@/components/bioinfoflow/logo"
import { useTranslations } from "next-intl"

const githubUrl = "https://github.com/lewismessthecode/BioinfoFlow"
const docsUrl = `${githubUrl}/tree/main/docs`

export function Footer() {
  const t = useTranslations("landing.footer")
  const primaryLinks = [
    { label: t("product.agent"), href: "#product" },
    { label: t("product.workflows"), href: "#features" },
    { label: t("legal.security"), href: "#security" },
    { label: t("resources.documentation"), href: docsUrl, external: true },
  ]

  return (
    <footer className="landing-footer-shell px-5 pb-8 pt-14 text-[var(--landing-cta-fg)] md:px-8 md:pb-10 md:pt-16">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-10 border-b border-white/12 pb-12 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start md:pb-16">
          <div>
            <Link
              href="/"
              className="inline-flex items-center gap-3 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--brand-accent)]"
            >
              <Logo size={30} className="text-[var(--landing-cta-fg)]" />
              <span className="text-sm font-semibold tracking-tight">Bioinfoflow</span>
            </Link>
            <p className="mt-5 max-w-sm text-sm leading-6 text-[color-mix(in_srgb,var(--landing-cta-fg)_58%,transparent)]">
              {t("tagline")}
            </p>
          </div>

          <nav aria-label={t("navigationLabel")}>
            <ul className="grid grid-cols-2 gap-x-8 gap-y-4 sm:flex sm:flex-wrap sm:justify-end">
              {primaryLinks.map((link) => (
                <li key={link.label}>
                  {link.external ? (
                    <a
                      href={link.href}
                      target="_blank"
                      rel="noreferrer"
                      className="landing-footer-link text-sm"
                    >
                      {link.label}
                      <ArrowUpRight className="size-3.5" />
                    </a>
                  ) : (
                    <Link href={link.href} className="landing-footer-link text-sm">
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <div className="landing-footer-wordmark mt-10 overflow-hidden border-b border-white/10 pb-4 md:mt-14 md:pb-6" aria-hidden="true">
          <p className="text-[clamp(3.25rem,10vw,8rem)] font-medium leading-none tracking-[-0.075em] opacity-[0.12]">
            Bioinfoflow
          </p>
        </div>

        <div className="flex flex-col gap-5 pt-6 text-xs text-[color-mix(in_srgb,var(--landing-cta-fg)_48%,transparent)] sm:flex-row sm:items-center sm:justify-between">
          <p>{t("copyright", { year: new Date().getFullYear() })}</p>
          <a
            href={githubUrl}
            target="_blank"
            rel="noreferrer"
            className="landing-footer-link text-xs"
          >
            <Github className="size-3.5" />
            GitHub
          </a>
        </div>
      </div>
    </footer>
  )
}
