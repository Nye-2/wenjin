"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Activity } from "lucide-react";

import { ChartContainer, DateRangePicker, KpiCard } from "./components";
import type { ExecutionStatsResponse } from "@/lib/api/admin-analytics";

const STATUS_COLORS: Record<string, string> = {
  completed: "#22c55e",
  completed_partial: "#84cc16",
  running: "#3b82f6",
  pending: "#94a3b8",
  failed: "#ef4444",
  cancelled: "#a1a1aa",
};

export function ExecutionPanel({
  data,
  range,
  onRangeChange,
}: {
  data: ExecutionStatsResponse | null;
  range: string;
  onRangeChange: (r: string) => void;
}) {
  const kpis = data?.kpis;

  // Flatten by_status into individual keys for recharts stacked bar
  const allStatuses = new Set<string>();
  for (const point of data?.time_series ?? []) {
    for (const s of Object.keys(point.by_status)) {
      allStatuses.add(s);
    }
  }
  const statusKeys = Array.from(allStatuses);

  const chartData = (data?.time_series ?? []).map((point) => {
    const row: Record<string, string | number> = { date: point.date };
    for (const s of statusKeys) {
      row[s] = point.by_status[s] ?? 0;
    }
    return row;
  });

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KpiCard
          label="执行总数"
          value={kpis?.total ?? 0}
          icon={<Activity className="w-5 h-5" />}
        />
        <KpiCard
          label="成功"
          value={kpis?.success ?? 0}
          trend={kpis && kpis.success_rate > 0.8 ? "up" : "neutral"}
        />
        <KpiCard
          label="失败"
          value={kpis?.failed ?? 0}
          trend={kpis && kpis.failed > 0 ? "down" : "neutral"}
        />
        <KpiCard
          label="成功率"
          value={
            kpis ? `${(kpis.success_rate * 100).toFixed(1)}%` : "0%"
          }
        />
      </div>
      <ChartContainer
        title="执行分布"
        actions={<DateRangePicker value={range} onChange={onRangeChange} />}
      >
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--wjn-line)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                stroke="var(--wjn-text-muted)"
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                stroke="var(--wjn-text-muted)"
                width={40}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--wjn-surface-subtle)",
                  border: "1px solid var(--wjn-line)",
                  borderRadius: "0.75rem",
                  fontSize: 12,
                }}
              />
              <Legend />
              {statusKeys.map((s) => (
                <Bar
                  key={s}
                  dataKey={s}
                  stackId="status"
                  fill={STATUS_COLORS[s] ?? "#94a3b8"}
                  name={s}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartContainer>
    </>
  );
}
