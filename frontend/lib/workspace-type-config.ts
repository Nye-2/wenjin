import type { Workspace } from "@/lib/api/types";

export interface WorkspaceWelcomeChip {
  label: string;
  prompt: string;
}

export interface WorkspaceWelcomeConfig {
  eyebrow: string;
  title: string;
  body: string;
  inputPlaceholder: string;
  chips: WorkspaceWelcomeChip[];
}

export interface WorkspaceTypeConfig {
  icon: string;
  title: string;
  chatSubtitle: string;
  panelSubtitle: string;
  welcome: WorkspaceWelcomeConfig;
}

export const WORKSPACE_TYPE_CONFIG: Record<
  Workspace["type"],
  WorkspaceTypeConfig
> = {
  thesis: {
    icon: "文",
    title: "论文工作台",
    chatSubtitle: "从选题到成稿，陪你推进",
    panelSubtitle: "学术研究与写作工作台",
    welcome: {
      eyebrow: "问津 · 论文工作台",
      title: "先把论文任务拆成下一步",
      body:
        "告诉我你的专业、题目、导师要求、已有材料，或者直接说你现在卡在哪里。问津会先帮你判断下一步该定题、找文献、搭大纲还是改正文。",
      inputPlaceholder: "说说你的论文题目、材料或眼前最想推进的问题...",
      chips: [
        {
          label: "确定选题",
          prompt: "我想先确定一个更稳的论文选题，我的专业和大致方向是：",
        },
        {
          label: "整理大纲",
          prompt: "帮我根据现有题目整理一版论文大纲，题目是：",
        },
        {
          label: "检查文献",
          prompt: "我想检查文献综述和论证是否够扎实，方向是：",
        },
        {
          label: "修改正文",
          prompt: "我有一段论文正文想修改，请先帮我判断问题：",
        },
      ],
    },
  },
  sci: {
    icon: "问",
    title: "SCI 论文工作台",
    chatSubtitle: "从研究问题到可投稿稿件",
    panelSubtitle: "SCI 论文发表工作台",
    welcome: {
      eyebrow: "问津 · SCI 论文工作台",
      title: "先把选题收紧，再让研究团队开跑",
      body:
        "告诉我研究方向、已有材料、目标期刊或你卡住的地方。问津会先和你把问题说清楚，再决定是否进入文献、方法、实验或写作推进。",
      inputPlaceholder: "说说你的研究方向、材料或想推进的问题...",
      chips: [
        {
          label: "梳理研究空白",
          prompt: "我想先梳理研究空白和可写创新点，方向是：",
        },
        {
          label: "收紧论文题目",
          prompt: "帮我把这个 SCI 选题收紧成可验证的问题：",
        },
        {
          label: "设计实验路线",
          prompt: "我想设计一条可复现实验路线，主题是：",
        },
        {
          label: "修改现有稿件",
          prompt: "我有一段论文内容想修改，请先帮我判断问题：",
        },
      ],
    },
  },
  proposal: {
    icon: "项",
    title: "申报书工作台",
    chatSubtitle: "把项目想法写成申报材料",
    panelSubtitle: "项目申报材料工作台",
    welcome: {
      eyebrow: "问津 · 申报书工作台",
      title: "先把项目故事讲清楚",
      body:
        "告诉我申报类别、研究基础、拟解决的问题和现有材料。问津会先帮你判断立项依据、研究内容、创新点和可行性哪里最需要补强。",
      inputPlaceholder: "说说申报类别、项目方向或材料缺口...",
      chips: [
        {
          label: "梳理立项依据",
          prompt: "帮我梳理申报书立项依据，我的项目方向是：",
        },
        {
          label: "凝练创新点",
          prompt: "我想把申报书创新点写得更清楚，现有想法是：",
        },
        {
          label: "设计研究内容",
          prompt: "帮我设计申报书的研究内容和技术路线，主题是：",
        },
        {
          label: "检查材料缺口",
          prompt: "帮我检查申报材料还缺哪些关键内容，项目类型是：",
        },
      ],
    },
  },
  software_copyright: {
    icon: "软",
    title: "软著工作台",
    chatSubtitle: "整理软著材料与技术说明",
    panelSubtitle: "软著申请材料工作台",
    welcome: {
      eyebrow: "问津 · 软著工作台",
      title: "先把软件说明变成可提交材料",
      body:
        "告诉我软件名称、使用场景、核心功能和已有截图或代码说明。问津会帮你把材料补齐成更适合软著申请的表达。",
      inputPlaceholder: "说说软件名称、功能模块或现有材料...",
      chips: [
        {
          label: "整理材料清单",
          prompt: "帮我整理软著申请材料清单，软件名称和用途是：",
        },
        {
          label: "提炼功能模块",
          prompt: "帮我把软件功能提炼成软著说明书里的模块，功能包括：",
        },
        {
          label: "起草技术说明",
          prompt: "我想起草软著技术说明，软件基本情况是：",
        },
        {
          label: "检查材料缺口",
          prompt: "帮我检查软著申请还缺哪些材料，我目前有：",
        },
      ],
    },
  },
  math_modeling: {
    icon: "Σ",
    title: "数学建模工作台",
    chatSubtitle: "先读赛题，再推进模型和论文",
    panelSubtitle: "数模竞赛论文工作台",
    welcome: {
      eyebrow: "问津 · 数学建模工作台",
      title: "先读题，再建模",
      body:
        "上传赛题 PDF 和附件数据，或者直接粘贴题面。问津会先拆问题、变量、约束和数据，再帮你选择模型路线与论文结构。",
      inputPlaceholder: "上传赛题 PDF，或描述题目、数据和你想先解决的问题...",
      chips: [
        {
          label: "上传赛题 PDF",
          prompt: "我准备上传数模赛题 PDF 和附件，请你先读题、拆解任务和数据需求。",
        },
        {
          label: "拆模型路线",
          prompt: "帮我拆解这道数模题的建模路线，题目大意是：",
        },
        {
          label: "生成求解代码",
          prompt: "我想先做求解代码和图表，题目数据情况是：",
        },
        {
          label: "整理论文结构",
          prompt: "帮我把数模论文结构先搭起来，赛题方向是：",
        },
      ],
    },
  },
  patent: {
    icon: "专",
    title: "专利工作台",
    chatSubtitle: "从技术方案到专利表达",
    panelSubtitle: "专利申请材料工作台",
    welcome: {
      eyebrow: "问津 · 专利工作台",
      title: "先把技术方案讲成专利语言",
      body:
        "告诉我技术领域、现有方案痛点、你的改进点和应用场景。问津会先帮你判断创新点、技术效果和权利要求支撑是否清楚。",
      inputPlaceholder: "说说技术方案、创新点或交底书材料...",
      chips: [
        {
          label: "梳理技术方案",
          prompt: "帮我梳理专利交底书技术方案，我的技术点是：",
        },
        {
          label: "提炼创新点",
          prompt: "我想提炼更清楚的专利创新点，现有方案是：",
        },
        {
          label: "起草权利要求",
          prompt: "帮我起草权利要求的初版，核心结构或流程是：",
        },
        {
          label: "检查交底书",
          prompt: "帮我检查专利交底书还缺什么支撑材料，我目前有：",
        },
      ],
    },
  },
};
