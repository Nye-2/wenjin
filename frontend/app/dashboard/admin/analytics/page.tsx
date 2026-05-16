"use client";

import { useEffect, useState } from "react";
import { TriangleAlert } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { UserGrowthPanel } from "./user-growth-panel";
import { ExecutionPanel } from "./execution-panel";
import { CreditPanel } from "./credit-panel";
import { WorkspaceAdoptionPanel } from "./workspace-adoption-panel";
import {
  getUserGrowth,
  getExecutionStats,
  getCreditConsumption,
  getWorkspaceAdoption,
  type UserGrowthResponse,
  type ExecutionStatsResponse,
  type CreditConsumptionResponse,
  type WorkspaceAdoptionResponse,
} from "@/lib/api/admin-analytics";

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export default function AnalyticsPage() {
  const [range, setRange] = useState("30d");

  const [userGrowth, setUserGrowth] = useState<UserGrowthResponse | null>(null);
  const [executionStats, setExecutionStats] = useState<ExecutionStatsResponse | null>(null);
  const [creditData, setCreditData] = useState<CreditConsumptionResponse | null>(null);
  const [workspaceData, setWorkspaceData] = useState<WorkspaceAdoptionResponse | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      getUserGrowth({ range, granularity: "day" }),
      getExecutionStats({ range, granularity: "day" }),
      getCreditConsumption({ range, granularity: "day" }),
      getWorkspaceAdoption(),
    ])
      .then(([ug, es, cc, wa]) => {
        if (!cancelled) {
          setUserGrowth(ug);
          setExecutionStats(es);
          setCreditData(cc);
          setWorkspaceData(wa);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(parseErrorMessage(err, "加载分析数据失败"));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [range, reloadNonce]);

  return (
    <>
      <AdminPageHeader
        title="数据分析"
        description="用户增长、执行统计、积分消费与空间采用趋势。"
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2 mb-4">
          <TriangleAlert className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="space-y-8">
        <UserGrowthPanel
          data={userGrowth}
          range={range}
          onRangeChange={setRange}
        />
        <ExecutionPanel
          data={executionStats}
          range={range}
          onRangeChange={setRange}
        />
        <CreditPanel
          data={creditData}
          range={range}
          onRangeChange={setRange}
        />
        <WorkspaceAdoptionPanel data={workspaceData} />
      </div>
    </>
  );
}
