"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export function KpiCard({
  label,
  value,
  hint,
  trend,
  icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
}) {
  const formattedValue =
    typeof value === "number" ? value.toLocaleString() : value;
  return (
    <div className="route-card rounded-2xl border border-[var(--wjn-line)] p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--wjn-text-secondary)]">{label}</span>
        {icon && <div className="text-[var(--wjn-navy)]">{icon}</div>}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-[var(--wjn-text)]">
          {formattedValue}
        </span>
        {trend === "up" && (
          <TrendingUp className="w-4 h-4 text-[var(--wjn-success)]" />
        )}
        {trend === "down" && (
          <TrendingDown className="w-4 h-4 text-[var(--wjn-error)]" />
        )}
        {trend === "neutral" && (
          <Minus className="w-4 h-4 text-[var(--wjn-text-muted)]" />
        )}
      </div>
      {hint && (
        <div className="mt-1 text-xs text-[var(--wjn-text-muted)]">{hint}</div>
      )}
    </div>
  );
}

export function DateRangePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (range: string) => void;
}) {
  const options = [
    { label: "7 天", value: "7d" },
    { label: "30 天", value: "30d" },
    { label: "90 天", value: "90d" },
  ];
  return (
    <div className="flex rounded-lg border border-[var(--wjn-line)] overflow-hidden">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs font-medium transition-colors ${
            value === opt.value
              ? "bg-[var(--wjn-navy)] text-white"
              : "bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function ChartContainer({
  title,
  children,
  actions,
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="route-card rounded-2xl border border-[var(--wjn-line)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-[var(--wjn-text)]">
          {title}
        </h3>
        {actions}
      </div>
      {children}
    </div>
  );
}
