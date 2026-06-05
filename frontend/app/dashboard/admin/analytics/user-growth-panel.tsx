"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Users } from "lucide-react";

import { ChartContainer, DateRangePicker, KpiCard } from "./components";
import type { UserGrowthResponse } from "@/lib/api/admin-analytics";

export function UserGrowthPanel({
  data,
  range,
  onRangeChange,
}: {
  data: UserGrowthResponse | null;
  range: string;
  onRangeChange: (r: string) => void;
}) {
  const kpis = data?.kpis;
  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KpiCard
          label="总用户"
          value={kpis?.total_users ?? 0}
          icon={<Users className="w-5 h-5" />}
        />
        <KpiCard
          label="新增注册"
          value={kpis?.new_in_range ?? 0}
          hint={`近 ${range === "7d" ? "7" : range === "30d" ? "30" : "90"} 天`}
        />
        <KpiCard
          label="DAU"
          value={kpis?.dau ?? 0}
          hint="24h 活跃"
        />
        <KpiCard
          label="WAU"
          value={kpis?.wau ?? 0}
          hint="7d 活跃"
        />
      </div>
      <ChartContainer
        title="注册趋势"
        actions={<DateRangePicker value={range} onChange={onRangeChange} />}
      >
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data?.time_series ?? []}>
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
              <Line
                type="monotone"
                dataKey="signups"
                stroke="var(--wjn-navy)"
                strokeWidth={2}
                dot={false}
                name="注册数"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartContainer>
    </>
  );
}
