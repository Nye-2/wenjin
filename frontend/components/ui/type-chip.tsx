import { cn } from "@/lib/utils";

/**
 * 材料类型 chip —— 两级命名规范的类型级。
 * 语义：回答「这是什么材料」，与 StatusPill（回答「到哪一步了」）互不混用。
 */
export const MATERIAL_TYPES = ["文献源", "数据", "代码", "结果", "图表", "材料"] as const;

export type MaterialType = (typeof MATERIAL_TYPES)[number];

/**
 * 后端 evidence/artifact 类型 → 中文类型标签映射表。
 * 超出五类的归并到最接近的一类。
 */
const TYPE_ALIAS: Record<string, MaterialType> = {
  paper: "文献源",
  source: "文献源",
  literature: "文献源",
  citation: "文献源",
  reference: "文献源",
  web: "文献源",
  web_page: "文献源",
  document: "文献源",
  dataset: "数据",
  data: "数据",
  statistics: "数据",
  code: "代码",
  script: "代码",
  notebook: "代码",
  result: "结果",
  computation: "结果",
  metric: "结果",
  output: "结果",
  artifact: "结果",
  figure: "图表",
  chart: "图表",
  visual: "图表",
  image: "图表",
  plot: "图表",
  upload: "材料",
  attachment: "材料",
  material: "材料",
};

export function resolveMaterialType(rawType: string | null | undefined): MaterialType {
  if (!rawType) return "数据";
  const hit = TYPE_ALIAS[rawType.toLowerCase()];
  return hit ?? "数据";
}

export function TypeChip({
  type,
  className,
}: {
  type: MaterialType;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded px-1.5 py-px text-[10px] font-medium leading-[1.6]",
        "bg-[rgba(28,36,32,0.06)] text-[var(--wjn-text-muted)]",
        className,
      )}
    >
      {type}
    </span>
  );
}
