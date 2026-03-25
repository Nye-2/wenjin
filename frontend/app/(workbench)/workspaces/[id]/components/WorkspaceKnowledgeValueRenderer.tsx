"use client";

import type { ReactNode } from "react";

function formatLabel(key: string): string {
  return key.replace(/[_-]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPrimitive(value: string | number | boolean | null): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

export function renderStructuredValue(
  value: unknown,
  depth: number = 0
): ReactNode {
  if (value === null || value === undefined) {
    return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
  }

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return (
      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--text-secondary)]">
        {formatPrimitive(value)}
      </p>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    const primitiveArray = value.every(
      (item) =>
        item === null || ["string", "number", "boolean"].includes(typeof item)
    );
    if (primitiveArray) {
      return (
        <div className="flex flex-wrap gap-2">
          {value.map((item, index) => (
            <span
              key={`${formatPrimitive(item as string | number | boolean | null)}-${index}`}
              className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
            >
              {formatPrimitive(item as string | number | boolean | null)}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div
            key={index}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium text-[var(--text-primary)]">
              Item {index + 1}
            </p>
            {renderStructuredValue(item, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    if (depth >= 3) {
      return (
        <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, entryValue]) => entryValue !== undefined
    );
    if (entries.length === 0) {
      return <p className="text-sm text-[var(--text-muted)]">暂无内容</p>;
    }

    return (
      <div className="space-y-3">
        {entries.map(([key, entryValue]) => (
          <div
            key={key}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3"
          >
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-primary)]">
              {formatLabel(key)}
            </p>
            {renderStructuredValue(entryValue, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-3 text-xs leading-6 text-[var(--text-secondary)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function DetailFieldGrid({
  fields,
}: {
  fields: Array<[label: string, value: ReactNode]>;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {fields.map(([label, value]) => (
        <div key={label} className="rounded-lg bg-[var(--bg-elevated)] px-3 py-2">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            {label}
          </p>
          <div className="mt-1 text-sm text-[var(--text-primary)]">{value}</div>
        </div>
      ))}
    </div>
  );
}
