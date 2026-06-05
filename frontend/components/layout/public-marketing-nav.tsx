"use client";

import Link from "next/link";

interface PublicMarketingNavProps {
  productLabel: string;
  docsLabel: string;
  pricingLabel?: string;
  workbenchLabel: string;
  active?: "docs" | "pricing";
}

export function PublicMarketingNav({
  productLabel,
  docsLabel,
  pricingLabel,
  workbenchLabel,
  active,
}: PublicMarketingNavProps) {
  const navLinkClass =
    "hidden min-h-11 items-center rounded-full px-4 text-sm font-bold text-[#344054] transition hover:bg-[#f2f4f7] sm:inline-flex";
  const activeClass = "bg-[#f2f4f7] text-[#101828]";

  return (
    <header className="border-b border-[rgba(16,24,40,0.08)] bg-[rgba(251,252,254,0.92)] backdrop-blur-xl">
      <nav className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-6 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-3 text-base font-bold">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#101828] text-sm font-black text-white">
            问
          </span>
          <span>问津 Wenjin</span>
        </Link>
        <div className="flex items-center gap-1">
          <Link href="/#product" className={navLinkClass}>
            {productLabel}
          </Link>
          <Link
            href="/docs"
            className={`${navLinkClass} ${active === "docs" ? activeClass : ""}`}
          >
            {docsLabel}
          </Link>
          {pricingLabel ? (
            <Link
              href="/pricing"
              className={`${navLinkClass} ${active === "pricing" ? activeClass : ""}`}
            >
              {pricingLabel}
            </Link>
          ) : null}
          <Link
            href="/workspaces"
            className="inline-flex min-h-11 items-center rounded-full bg-[#101828] px-4 text-sm font-bold text-white shadow-[0_14px_34px_rgba(16,24,40,0.18)] transition hover:bg-[#1f2937]"
          >
            {workbenchLabel}
          </Link>
        </div>
      </nav>
    </header>
  );
}
