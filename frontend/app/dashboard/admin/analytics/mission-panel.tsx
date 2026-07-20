"use client";

import { Activity } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MissionStatsResponse } from "@/lib/api/admin-analytics";
import { ChartContainer, DateRangePicker, KpiCard } from "./components";

const STATUS_COLORS: Record<string, string> = {
  completed: "var(--wjn-success)",
  running: "var(--wjn-blue)",
  planning: "var(--wjn-blue)",
  waiting: "var(--wjn-review)",
  failed: "var(--wjn-error)",
  cancelled: "var(--wjn-text-muted)",
};

export function MissionPanel({
  data,
  range,
  onRangeChange,
}: {
  data: MissionStatsResponse | null;
  range: string;
  onRangeChange: (range: string) => void;
}) {
  const kpis = data?.kpis;
  const statuses = Array.from(
    new Set(
      (data?.time_series ?? []).flatMap((point) => Object.keys(point.by_status)),
    ),
  );
  const chartData = (data?.time_series ?? []).map((point) => ({
    date: point.date,
    ...Object.fromEntries(statuses.map((status) => [status, point.by_status[status] ?? 0])),
  }));

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="任务总数" value={kpis?.total ?? 0} icon={<Activity className="h-5 w-5" />} />
        <KpiCard label="完成" value={kpis?.success ?? 0} trend={kpis && kpis.success_rate > 0.8 ? "up" : "neutral"} />
        <KpiCard label="未完成" value={kpis?.failed ?? 0} trend={kpis && kpis.failed > 0 ? "down" : "neutral"} />
        <KpiCard label="完成率" value={kpis ? `${(kpis.success_rate * 100).toFixed(1)}%` : "0%"} />
      </div>
      <ChartContainer title="研究任务分布" actions={<DateRangePicker value={range} onChange={onRangeChange} />}>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--wjn-line)" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="var(--wjn-text-muted)" tickFormatter={(value: string) => value.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} stroke="var(--wjn-text-muted)" width={40} />
              <Tooltip contentStyle={{ background: "var(--wjn-surface-subtle)", border: "1px solid var(--wjn-line)", borderRadius: "var(--wjn-radius)", fontSize: 12 }} />
              <Legend />
              {statuses.map((status) => <Bar key={status} dataKey={status} stackId="status" fill={STATUS_COLORS[status] ?? "var(--wjn-text-muted)"} name={status} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartContainer>
    </>
  );
}
