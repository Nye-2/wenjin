"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { FolderOpen } from "lucide-react";

import { ChartContainer, KpiCard } from "./components";
import type { WorkspaceAdoptionResponse } from "@/lib/api/admin-analytics";

const PALETTE = [
  "var(--wjn-blue)",
  "var(--wjn-blue)",
  "var(--wjn-blue)",
  "var(--wjn-review)",
  "var(--wjn-error)",
  "var(--wjn-blue)",
  "var(--wjn-blue)",
  "var(--wjn-blue)",
];

const WORKSPACE_LABELS: Record<string, string> = {
  thesis: "论文",
  sci: "科研",
  proposal: "课题",
  software_copyright: "软著",
  patent: "专利",
};

export function WorkspaceAdoptionPanel({
  data,
}: {
  data: WorkspaceAdoptionResponse | null;
}) {
  const pieData = (data?.by_type ?? []).map((item) => ({
    name: WORKSPACE_LABELS[item.type] ?? item.type,
    value: item.count,
  }));

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KpiCard
          label="工作空间总数"
          value={data?.total_workspaces ?? 0}
          icon={<FolderOpen className="w-5 h-5" />}
        />
        <KpiCard
          label="创建用户"
          value={data?.users_with_workspaces ?? 0}
          hint="至少有一个空间"
        />
        <KpiCard
          label="采用率"
          value={
            data
              ? `${(data.adoption_rate * 100).toFixed(1)}%`
              : "0%"
          }
        />
      </div>
      <ChartContainer title="空间类型分布">
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
              >
                {pieData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={PALETTE[i % PALETTE.length]}
                    stroke="none"
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "var(--wjn-surface-subtle)",
                  border: "1px solid var(--wjn-line)",
                  borderRadius: "0.75rem",
                  fontSize: 12,
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </ChartContainer>
    </>
  );
}
