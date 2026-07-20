"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { CreditCard } from "lucide-react";

import { ChartContainer, DateRangePicker, KpiCard } from "./components";
import type { CreditConsumptionResponse } from "@/lib/api/admin-analytics";

export function CreditPanel({
  data,
  range,
  onRangeChange,
}: {
  data: CreditConsumptionResponse | null;
  range: string;
  onRangeChange: (r: string) => void;
}) {
  const kpis = data?.kpis;
  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KpiCard
          label="已发放"
          value={kpis?.total_issued ?? 0}
          icon={<CreditCard className="w-5 h-5" />}
        />
        <KpiCard
          label="已消费"
          value={kpis?.total_spent ?? 0}
        />
        <KpiCard
          label="当前余额池"
          value={kpis?.current_pool ?? 0}
        />
      </div>
      <ChartContainer
        title="积分流水"
        actions={<DateRangePicker value={range} onChange={onRangeChange} />}
      >
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data?.credit_series ?? []}>
              <defs>
                <linearGradient id="inflowGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--wjn-success)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--wjn-success)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="outflowGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--wjn-error)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--wjn-error)" stopOpacity={0} />
                </linearGradient>
              </defs>
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
              <Area
                type="monotone"
                dataKey="inflow"
                stroke="var(--wjn-success)"
                fill="url(#inflowGrad)"
                strokeWidth={2}
                name="流入"
              />
              <Area
                type="monotone"
                dataKey="outflow"
                stroke="var(--wjn-error)"
                fill="url(#outflowGrad)"
                strokeWidth={2}
                name="流出"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartContainer>
    </>
  );
}
