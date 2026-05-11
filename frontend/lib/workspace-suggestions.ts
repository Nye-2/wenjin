import type { Workspace } from "@/lib/api/types";

export interface WorkspaceTypeConfig {
  icon: string;
  title: string;
  chatSubtitle: string;
  panelSubtitle: string;
  suggestions: string[];
}

export const WORKSPACE_TYPE_CONFIG: Record<
  Workspace["type"],
  WorkspaceTypeConfig
> = {
  thesis: {
    icon: "📝",
    title: "论文工作台",
    chatSubtitle: "告诉我你想做什么，我来帮你",
    panelSubtitle: "AI 驱动的学术研究与写作助手",
    suggestions: ["帮我做个大纲", "检索相关文献", "写文献综述", "深度调研"],
  },
  sci: {
    icon: "🔬",
    title: "SCI 论文工作台",
    chatSubtitle: "从检索到发表，全流程辅助",
    panelSubtitle: "AI 驱动的 SCI 论文发表助手",
    suggestions: ["检索文献", "分析这篇论文", "写文献综述", "生成论文框架"],
  },
  proposal: {
    icon: "📋",
    title: "申报书工作台",
    chatSubtitle: "从调研到申报，高效推进",
    panelSubtitle: "AI 驱动的项目申报助手",
    suggestions: ["生成申报书大纲", "做背景调研", "设计实验方案"],
  },
  software_copyright: {
    icon: "💻",
    title: "软著工作台",
    chatSubtitle: "软著材料准备与技术说明",
    panelSubtitle: "AI 驱动的软著申请助手",
    suggestions: ["准备软著材料", "写技术说明"],
  },
  patent: {
    icon: "🔧",
    title: "专利工作台",
    chatSubtitle: "专利框架与现有技术检索",
    panelSubtitle: "AI 驱动的专利申请助手",
    suggestions: ["生成专利框架", "检索现有技术"],
  },
};
