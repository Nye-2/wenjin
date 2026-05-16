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
    <div className="route-card rounded-2xl border border-[var(--border-default)] p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--text-secondary)]">{label}</span>
        {icon && <div className="text-[var(--accent-primary)]">{icon}</div>}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-[var(--text-primary)]">
          {formattedValue}
        </span>
        {trend === "up" && (
          <TrendingUp className="w-4 h-4 text-emerald-500" />
        )}
        {trend === "down" && (
          <TrendingDown className="w-4 h-4 text-rose-500" />
        )}
        {trend === "neutral" && (
          <Minus className="w-4 h-4 text-[var(--text-muted)]" />
        )}
      </div>
      {hint && (
        <div className="mt-1 text-xs text-[var(--text-muted)]">{hint}</div>
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
    <div className="flex rounded-lg border border-[var(--border-default)] overflow-hidden">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs font-medium transition-colors ${
            value === opt.value
              ? "bg-[var(--accent-primary)] text-white"
              : "bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
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
    <div className="route-card rounded-2xl border border-[var(--border-default)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">
          {title}
        </h3>
        {actions}
      </div>
      {children}
    </div>
  );
}
