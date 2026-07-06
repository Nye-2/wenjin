import type { Workspace } from "@/lib/api/types";

export interface WorkspaceTypeConfig {
  icon: string;
  title: string;
  chatSubtitle: string;
  panelSubtitle: string;
  suggestions: string[];
  intakeGuidance?: {
    checklist: string[];
    chips: string[];
  };
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
    intakeGuidance: {
      checklist: [
        "论文题目或研究方向",
        "学校、学院或导师的格式要求",
        "已有大纲、初稿、文献或数据材料",
        "这次最想推进的章节或问题",
      ],
      chips: [
        "我有题目和初稿，帮我梳理下一步",
        "先帮我确认论文方向和大纲",
        "根据已有材料做文献与论证检查",
      ],
    },
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
    intakeGuidance: {
      checklist: [
        "软件名称和 Web / App / 桌面端形态",
        "核心功能清单和用户角色",
        "运行截图、界面材料或现有代码说明",
        "技术栈、后端语言和必须强调的功能点",
      ],
      chips: [
        "先帮我整理软著材料清单",
        "我有软件功能，帮我写技术说明",
        "帮我确认软著申请还缺哪些材料",
      ],
    },
  },
  math_modeling: {
    icon: "Σ",
    title: "数学建模工作台",
    chatSubtitle: "从赛题到论文包，一步推进",
    panelSubtitle: "AI 驱动的数模竞赛论文助手",
    suggestions: ["生成数模论文包", "解析赛题并建模", "生成图表和求解代码"],
    intakeGuidance: {
      checklist: [
        "赛题题面和数据附件",
        "竞赛格式、字数或模板要求",
        "想优先解决的问题和建模方向",
        "是否需要图表、Python 代码和论文包",
      ],
      chips: [
        "我有赛题和数据，帮我整理建模思路",
        "先解析赛题并列出变量和约束",
        "帮我生成数模论文包和 Python 方案",
      ],
    },
  },
  patent: {
    icon: "🔧",
    title: "专利工作台",
    chatSubtitle: "专利框架与现有技术检索",
    panelSubtitle: "AI 驱动的专利申请助手",
    suggestions: ["生成专利框架", "检索现有技术"],
    intakeGuidance: {
      checklist: [
        "发明名称和技术领域",
        "现有方案、痛点和应用场景",
        "核心创新点与可替代方案",
        "图示、流程、实施例或实验材料",
      ],
      chips: [
        "我有技术点，帮我梳理专利交底书",
        "先检索现有技术并找差异点",
        "帮我检查权利要求还缺什么支撑",
      ],
    },
  },
};
