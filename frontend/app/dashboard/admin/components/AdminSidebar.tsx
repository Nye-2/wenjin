"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bot,
  Coins,
  Layers,
  LayoutDashboard,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";

const TOP: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin", label: "概览", icon: LayoutDashboard },
  { href: "/dashboard/admin/users", label: "用户管理", icon: Users },
];

const CREDIT_GROUP = {
  label: "积分中心",
  icon: Coins,
  children: [
    { href: "/dashboard/admin/credits", label: "流水" },
    { href: "/dashboard/admin/credits/rules", label: "发放规则" },
    { href: "/dashboard/admin/credits/redeem-codes", label: "兑换码" },
    { href: "/dashboard/admin/credits/pricing", label: "定价策略" },
  ],
};

const BUSINESS: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin/models", label: "模型管理", icon: Bot },
  { href: "/dashboard/admin/capabilities", label: "Capability", icon: Layers },
  { href: "/dashboard/admin/skills", label: "Skill", icon: Wrench },
  { href: "/dashboard/admin/analytics", label: "数据分析", icon: BarChart3 },
];

const SYSTEM: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin/mcp", label: "MCP 配置", icon: Settings },
  { href: "/dashboard/admin/release-gate", label: "发布门禁", icon: ShieldCheck },
  { href: "/dashboard/admin/logs", label: "操作日志", icon: ScrollText },
];

export function AdminSidebar() {
  const pathname = usePathname() ?? "";

  const isActive = (href: string) => {
    if (href === "/dashboard/admin") return pathname === href;
    return pathname.startsWith(href);
  };

  return (
    <aside className="w-60 shrink-0 border-r border-[var(--border-default)] bg-[var(--bg-surface)] min-h-[calc(100vh-4rem)] hidden lg:block">
      <nav className="flex flex-col gap-1 p-4 text-sm">
        {TOP.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}

        <div className="mt-2">
          <div className="flex items-center gap-2 px-3 py-2 text-[var(--text-muted)] text-xs uppercase tracking-wide">
            <CREDIT_GROUP.icon className="w-4 h-4" />
            {CREDIT_GROUP.label}
          </div>
          <div className="ml-4 flex flex-col gap-1">
            {CREDIT_GROUP.children.map((child) => (
              <Link
                key={child.href}
                href={child.href}
                className={`rounded-lg px-3 py-1.5 transition-colors ${
                  isActive(child.href)
                    ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                }`}
              >
                {child.label}
              </Link>
            ))}
          </div>
        </div>

        {BUSINESS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}

        <div className="my-2 border-t border-[var(--border-default)]" />

        {SYSTEM.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
