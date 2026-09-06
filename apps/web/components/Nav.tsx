"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/verify", label: "Verify" },
  { href: "/about", label: "How it works" },
];

export function Nav({ minimal = false }: { minimal?: boolean }) {
  const pathname = usePathname();

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "20px 0",
        borderBottom: minimal ? "none" : "1px solid var(--line)",
      }}
    >
      <Link
        href="/"
        style={{
          fontSize: 15,
          fontWeight: 600,
          letterSpacing: "0.14em",
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        RAYA
      </Link>

      <nav style={{ display: "flex", gap: 4 }}>
        {LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              style={{
                fontSize: 13.5,
                padding: "7px 12px",
                borderRadius: "var(--radius)",
                color: active ? "var(--ink)" : "var(--ink-tertiary)",
                background: active ? "var(--bg-inset)" : "transparent",
                transition: "color var(--dur-fast) var(--ease)",
              }}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
