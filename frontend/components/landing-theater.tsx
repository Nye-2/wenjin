"use client";

import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  Loader2,
  Sparkles,
  Stamp,
} from "lucide-react";

const serif = '"Songti SC", "STSong", "Noto Serif SC", Georgia, "Times New Roman", serif';

const PAPER_DEEP = "#EFE9DC";
const SURFACE = "#FDFBF5";
const INK = "#1C2420";
const INK_SOFT = "rgba(28, 36, 32, 0.64)";
const INK_FAINT = "rgba(28, 36, 32, 0.42)";
const LINE = "rgba(28, 36, 32, 0.10)";
const BRASS = "#B5852F";

// step: 0 初始 → 1 用户提问 → 2 状态行 → 3 回复 → 4/5/6 阶段点亮+证据落入 → 7 待确认 → 8 已确认 → 9 淡出重置
const STEP_MS = [700, 1500, 1300, 1700, 1700, 1700, 1700, 1600, 3400, 800];

const STAGES = ["梳理预测对象与变量符号", "检索并查证 6 篇相关文献", "起草模型规格与实验计划"];

const EVIDENCE = [
  { title: "Li et al. 2024", sub: "Bike-sharing demand: a spatiotemporal survey", kind: "文献源", tag: "已查证" },
  { title: "Census 出行报告", sub: "城市慢行交通年度统计", kind: "数据", tag: "已查证" },
  { title: "需求预测基线图", sub: "20 个站点逐小时借还量基线", kind: "图表", tag: "待你确认" },
];

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export default function DemoTheater({
  accent: ACCENT,
  soft: ACCENT_SOFT,
  panel: PANEL_BG = PAPER_DEEP,
  meta: META = BRASS,
  surface: SURFACE_BG = SURFACE,
}: {
  accent: string;
  soft: string;
  panel?: string;
  meta?: string;
  surface?: string;
}) {
  const [step, setStep] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) {
      setStep(8);
      return;
    }
    const t = window.setTimeout(() => {
      setStep((s) => (s >= STEP_MS.length - 1 ? 0 : s + 1));
    }, STEP_MS[step]);
    return () => window.clearTimeout(t);
  }, [step, reduced]);

  const stageDone = (i: number) => step >= 4 + i;
  const stageActive = (i: number) => step === 3 + i;
  const confirmed = step >= 8;

  return (
    <div
      className="overflow-hidden rounded-[18px] border shadow-[0_40px_90px_rgba(28,36,32,0.16)]"
      style={{ borderColor: LINE, background: SURFACE_BG, opacity: step === 9 ? 0 : 1, transition: "opacity 700ms ease" }}
    >
      {/* window bar */}
      <div className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: LINE }}>
        <div className="flex items-center gap-2">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2.5 w-2.5 rounded-full" style={{ background: "#E0D7C4" }} />
          ))}
        </div>
        <span className="flex items-center gap-2 text-[11px] tracking-[0.18em]" style={{ color: INK_FAINT }}>
          数学建模工作台
          {step >= 2 && !confirmed && (
            <span className="flex items-center gap-1.5" style={{ color: ACCENT }}>
              <Loader2 size={11} className="animate-spin" />
              研究进行中
            </span>
          )}
          {confirmed && (
            <span className="flex items-center gap-1.5" style={{ color: ACCENT }}>
              <CheckCircle2 size={11} />
              成果已确认
            </span>
          )}
        </span>
        <span
          className="rounded-full px-2 py-0.5 text-[9px] font-semibold tracking-[0.14em]"
          style={{ background: ACCENT_SOFT, color: ACCENT }}
        >
          实时演示
        </span>
      </div>

      <div className="grid md:grid-cols-[1.25fr_1fr]">
        {/* chat side */}
        <div className="min-h-[380px] border-r px-7 py-6" style={{ borderColor: LINE }}>
          {/* user bubble */}
          <div
            className="flex justify-end transition-all duration-500"
            style={{ opacity: step >= 1 ? 1 : 0, transform: step >= 1 ? "none" : "translateY(10px)" }}
          >
            <div
              className="max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-3 text-[12.5px] leading-[1.75] text-[#F5F1E8]"
              style={{ background: INK }}
            >
              先完成问题一：需求预测模型设计，必须给出变量、目标、公式与可复现实验计划。
            </div>
          </div>

          {/* status line */}
          <div
            className="mt-5 flex items-center gap-2 text-[11.5px] transition-all duration-500"
            style={{ color: ACCENT, opacity: step >= 2 ? 1 : 0, transform: step >= 2 ? "none" : "translateY(8px)" }}
          >
            <Sparkles size={13} />
            <span className="font-medium">研究任务已开始</span>
            <span style={{ color: INK_FAINT }}>· 3 个阶段已排定</span>
          </div>

          {/* assistant reply */}
          <p
            className="mt-3 text-[13px] leading-[1.85] transition-all duration-500"
            style={{ color: INK_SOFT, opacity: step >= 3 ? 1 : 0, transform: step >= 3 ? "none" : "translateY(8px)" }}
          >
            已开始「共享单车需求预测模型设计」。我会先梳理预测对象与时空粒度，建立可解释的统计模型族，
            再把每一处假设和引用留在右侧的来源页里——你可以随时追问任何一步。
          </p>

          {/* stages */}
          <div className="mt-5 space-y-2">
            {STAGES.map((label, i) => (
              <div
                key={label}
                className="flex items-center gap-2.5 text-[12px] transition-all duration-500"
                style={{
                  color: stageDone(i) ? INK_SOFT : INK_FAINT,
                  opacity: step >= 3 ? 1 : 0,
                  transform: step >= 3 ? "none" : "translateY(8px)",
                }}
              >
                {stageDone(i) ? (
                  <CheckCircle2 size={14} style={{ color: ACCENT }} />
                ) : stageActive(i) ? (
                  <Loader2 size={14} className="animate-spin" style={{ color: META }} />
                ) : (
                  <span className="h-[14px] w-[14px] rounded-full border" style={{ borderColor: "#C9BFA9" }} />
                )}
                {label}
              </div>
            ))}
          </div>
        </div>

        {/* evidence side */}
        <div className="min-h-[380px] px-7 py-6" style={{ background: PANEL_BG }}>
          <div className="text-[10.5px] font-semibold tracking-[0.26em]" style={{ color: META }}>
            来源与结果 · SOURCES & RESULTS
          </div>
          <div className="mt-4 space-y-3">
            {EVIDENCE.map((e, i) => (
              <div
                key={e.title}
                className="rounded-xl border px-4 py-3 transition-all duration-500"
                style={{
                  borderColor: LINE,
                  background: SURFACE_BG,
                  opacity: stageDone(i) ? 1 : 0,
                  transform: stageDone(i) ? "none" : "translateX(14px)",
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-[12.5px] font-semibold" style={{ color: INK, fontFamily: serif }}>
                    <span
                      className="rounded px-1.5 py-px text-[10px] font-medium"
                      style={{ background: "rgba(28,36,32,0.06)", color: INK_FAINT, fontFamily: "inherit" }}
                    >
                      {e.kind}
                    </span>
                    {e.title}
                  </span>
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                    style={
                      e.tag === "已查证"
                        ? { background: ACCENT_SOFT, color: ACCENT }
                        : { background: "rgba(181,133,47,0.12)", color: BRASS }
                    }
                  >
                    {e.tag}
                  </span>
                </div>
                <div className="mt-1 text-[11.5px]" style={{ color: INK_FAINT }}>
                  {e.sub}
                </div>
              </div>
            ))}
          </div>

          {/* review banner */}
          <div
            className="mt-5 flex items-center justify-between rounded-xl px-4 py-3 text-[12px] transition-all duration-500"
            style={{
              background: INK,
              opacity: step >= 7 ? 1 : 0,
              transform: step >= 7 ? "none" : "translateY(10px)",
            }}
          >
            <span className="flex items-center gap-2 text-[#F5F1E8]">
              {confirmed && <Stamp size={13} className="text-[#E8D9B8]" />}
              {confirmed ? "已确认 · 已写入论文初稿" : "第一问成果已就绪"}
            </span>
            {!confirmed && (
              <span className="flex items-center gap-1 font-medium text-[#E8D9B8]">
                去确认 <ArrowUpRight size={13} />
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
