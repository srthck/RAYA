"use client";

/**
 * A light, floating navigation bar.
 *
 * Sticky and translucent so the page appears to pass beneath a sheet of ice
 * rather than scrolling under an opaque slab. It stays deliberately small: the
 * product has three destinations and does not need more.
 */

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
      className="nav-bar"
      data-flush={minimal ? "true" : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--s4)",
        padding: "14px 0",
        height: "var(--nav-h, 58px)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--s4)", minWidth: 0 }}>
        <Link
          href="/"
          aria-label="RAYA home"
          style={{
            fontSize: 15,
            fontWeight: 640,
            letterSpacing: "0.16em",
            color: "var(--ink)",
            flex: "none",
          }}
        >
          RAYA
        </Link>
        <span
          className="nav-tagline label"
          style={{
            fontSize: 9.5,
            letterSpacing: "0.16em",
            color: "var(--ink-quaternary)",
            paddingLeft: "var(--s4)",
            borderLeft: "1px solid var(--line)",
            whiteSpace: "nowrap",
          }}
        >
          Visual evidence verification
        </span>
      </div>

      <nav aria-label="Primary" style={{ display: "flex", gap: 2 }}>
        {LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              style={{
                position: "relative",
                fontSize: 13.5,
                fontWeight: active ? 560 : 460,
                padding: "7px 13px",
                borderRadius: "var(--radius)",
                color: active ? "var(--ink)" : "var(--ink-tertiary)",
                transition:
                  "color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease)",
              }}
            >
              {link.label}
              {/* The active marker is a thin water line, not a filled chip. */}
              {active && (
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: 13,
                    right: 13,
                    bottom: 2,
                    height: 1.5,
                    borderRadius: 2,
                    background: "var(--accent)",
                  }}
                />
              )}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
