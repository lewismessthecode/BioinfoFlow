"use client"

import Link from "next/link"
import { Github, Twitter, Linkedin } from "@/lib/icons"
import { Logo } from "@/components/bioinfoflow/logo"
import { useTranslations } from "next-intl"

const socialLinks = [
  { icon: Github, href: "#", label: "GitHub" },
  { icon: Twitter, href: "#", label: "Twitter" },
  { icon: Linkedin, href: "#", label: "LinkedIn" },
]

export function Footer() {
  const t = useTranslations("landing.footer")

  const footerLinks = {
    product: {
      title: t("product.title"),
      links: [
        { label: t("product.agent"), href: "#" },
        { label: t("product.workflows"), href: "#" },
        { label: t("product.runs"), href: "#" },
        { label: t("product.images"), href: "#" },
        { label: t("product.changelog"), href: "#" },
      ],
    },
    resources: {
      title: t("resources.title"),
      links: [
        { label: t("resources.documentation"), href: "#" },
        { label: t("resources.apiReference"), href: "#" },
        { label: t("resources.tutorials"), href: "#" },
        { label: t("resources.blog"), href: "#" },
      ],
    },
    company: {
      title: t("company.title"),
      links: [
        { label: t("company.about"), href: "#" },
        { label: t("company.careers"), href: "#" },
        { label: t("company.contact"), href: "#" },
      ],
    },
    legal: {
      title: t("legal.title"),
      links: [
        { label: t("legal.privacy"), href: "#" },
        { label: t("legal.terms"), href: "#" },
        { label: t("legal.security"), href: "#" },
      ],
    },
  }

  return (
    <footer className="border-t border-border bg-background">
      <div className="container mx-auto px-6 py-16">
        {/* Main Footer Content */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 mb-12">
          {/* Brand Column */}
          <div className="col-span-2 md:col-span-4 lg:col-span-1 mb-8 lg:mb-0">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center">
                <Logo size={32} className="text-foreground" />
              </div>
              <span className="font-semibold text-lg tracking-tight">Bioinfoflow</span>
            </Link>
            <p className="text-sm text-muted-foreground leading-relaxed mb-6 max-w-xs">
              {t("tagline")}
            </p>

            {/* Social Links */}
            <div className="flex gap-3">
              {socialLinks.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-foreground/20 transition-colors"
                  aria-label={social.label}
                >
                  <social.icon className="w-4 h-4" />
                </a>
              ))}
            </div>
          </div>

          {/* Link Columns */}
          {Object.values(footerLinks).map((section) => (
            <div key={section.title}>
              <h3 className="font-medium text-sm mb-4">{section.title}</h3>
              <ul className="space-y-3">
                {section.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-muted-foreground">
            {t("copyright", { year: new Date().getFullYear() })}
          </p>
          <p className="text-sm text-muted-foreground">
            {t("bottomTagline")}
          </p>
        </div>
      </div>
    </footer>
  )
}
