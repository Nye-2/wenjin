"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Clock3,
  Code2,
  FileText,
  FlaskConical,
  Lightbulb,
  Loader2,
  Plus,
  Search,
  Sigma,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { WORKSPACE_TYPES, type WorkspaceType } from "@/lib/workspace-types";
import { useWorkspaceStore, Workspace } from "@/stores/workspace";
import { useAuthStore } from "@/stores/auth";

const serif = "var(--wjn-font-serif)";

const workspaceTypeIcons: Record<WorkspaceType, typeof FileText> = {
  sci: FileText,
  thesis: BookOpen,
  proposal: FlaskConical,
  software_copyright: Code2,
  math_modeling: Sigma,
  patent: Lightbulb,
};

const workspaceTypeLabels: Record<WorkspaceType, string> = {
  sci: "SCI论文",
  thesis: "本科毕业论文",
  proposal: "项目申报书",
  software_copyright: "软件著作权申报",
  math_modeling: "数学建模论文竞赛",
  patent: "专利申请",
};

const workspaceTargetOutputs: Record<WorkspaceType, string> = {
  sci: "论文初稿与修订计划",
  thesis: "毕业论文结构与章节草稿",
  proposal: "申报书初稿与实验设计说明",
  software_copyright: "材料清单与技术说明书",
  math_modeling: "建模论文、求解代码与结果验证",
  patent: "专利框架与交付清单",
};

const workspaceNextSteps: Record<WorkspaceType, string> = {
  sci: "继续补充文献来源并生成章节框架",
  thesis: "补齐开题背景并推进正文结构设计",
  proposal: "整理背景调研并继续实验设计",
  software_copyright: "补全材料项并继续技术说明撰写",
  math_modeling: "上传或确认题目，继续模型构建与结果验证",
  patent: "继续现有技术检索并提炼创新点",
};

const workspaceTypes = WORKSPACE_TYPES.map((value) => ({
  value,
  label: workspaceTypeLabels[value],
}));

const disciplineLabels = new Map<string, string>([
  ["computer_science", "计算机科学"],
  ["physics", "物理学"],
  ["biology", "生物学"],
  ["chemistry", "化学"],
  ["medicine", "医学"],
  ["engineering", "工程学"],
  ["social_science", "社会科学"],
  ["humanities", "人文学科"],
]);

function formatDiscipline(value: string | null | undefined): string | null {
  if (!value) return null;
  return disciplineLabels.get(value) ?? value.replace(/_/g, " ");
}

const disciplines = [
  { value: "computer_science", label: "计算机科学" },
  { value: "physics", label: "物理学" },
  { value: "biology", label: "生物学" },
  { value: "chemistry", label: "化学" },
  { value: "medicine", label: "医学" },
  { value: "engineering", label: "工程学" },
  { value: "social_science", label: "社会科学" },
  { value: "humanities", label: "人文学科" },
];

function formatWorkspaceDate(dateString: string) {
  const date = new Date(dateString);
  return date.toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function WorkspaceRouteCard({
  workspace,
  typeLabel,
  targetOutput,
  nextAction,
  onOpen,
  onDelete,
}: {
  workspace: Workspace;
  typeLabel: string;
  targetOutput: string;
  nextAction: string;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <motion.article
      layout
      initial={{ opacity: 0.88, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      className="group relative overflow-hidden rounded-[16px] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-6 transition-all hover:-translate-y-[3px] hover:shadow-[var(--wjn-shadow-md)]"
    >
      <div className="absolute right-4 top-4 z-10 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          className="rounded-full border border-[rgba(179,52,62,0.24)] bg-[var(--wjn-surface)] p-2 text-[var(--wjn-error)] transition-colors hover:bg-[var(--wjn-error-soft)]"
          aria-label="删除工作空间"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <button type="button" onClick={onOpen} className="flex w-full flex-col text-left">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span className="inline-flex items-center rounded-full bg-[var(--wjn-surface-subtle)] px-2.5 py-[3px] text-[11px] font-medium text-[var(--wjn-text-secondary)]">
              {typeLabel}
            </span>
            <h3
              className="mt-3 truncate text-[19px] font-bold leading-snug tracking-[0.01em] text-[var(--wjn-text)]"
              style={{ fontFamily: serif }}
            >
              {workspace.name}
            </h3>
            <p className="mt-2 line-clamp-2 max-w-[560px] text-[13px] leading-[1.8] text-[var(--wjn-text-secondary)]">
              {workspace.description?.trim() || formatDiscipline(workspace.discipline) || targetOutput}
            </p>
          </div>
          <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--wjn-line)] text-[var(--wjn-text-secondary)] transition-all group-hover:border-transparent group-hover:bg-[var(--wjn-blue)] group-hover:text-[#f5f1e8]">
            <ArrowUpRight className="h-4 w-4" />
          </span>
        </div>

        <div className="mt-5 flex items-center gap-2 text-[12px] text-[var(--wjn-text-secondary)]">
          <Sparkles className="h-3.5 w-3.5 text-[var(--wjn-review)]" aria-hidden="true" />
          <span className="font-medium text-[var(--wjn-text)]">下一步</span>
          {nextAction}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-[var(--wjn-line)] pt-4">
          <div className="flex items-center gap-4 text-[11.5px] text-[var(--wjn-text-muted)]">
            <span className="flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
              {formatWorkspaceDate(workspace.updated_at)}
            </span>
            <span className="hidden sm:inline">目标产物 · {targetOutput}</span>
          </div>
          <span className="flex items-center gap-1 text-[12.5px] font-medium text-[var(--wjn-blue)]">
            进入工作台
            <ArrowRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </button>
    </motion.article>
  );
}

export default function WorkspacesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newWorkspace, setNewWorkspace] = useState({
    name: "",
    type: "sci" as WorkspaceType,
    discipline: "",
    description: "",
  });

  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const isWorkspacesLoading = useWorkspaceStore((state) => state.isWorkspacesLoading);
  const isWorkspaceMutating = useWorkspaceStore((state) => state.isWorkspaceMutating);
  const error = useWorkspaceStore((state) => state.error);
  const fetchWorkspaces = useWorkspaceStore((state) => state.fetchWorkspaces);
  const createWorkspace = useWorkspaceStore((state) => state.createWorkspace);
  const removeWorkspace = useWorkspaceStore((state) => state.removeWorkspace);
  const clearError = useWorkspaceStore((state) => state.clearError);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, authLoading, router]);

  useEffect(() => {
    void fetchWorkspaces();
  }, [fetchWorkspaces]);

  const sortedWorkspaces = useMemo(
    () =>
      [...workspaces].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      ),
    [workspaces]
  );

  const typeCounts = useMemo(() => {
    const counts = new Map<WorkspaceType, number>();
    for (const workspace of workspaces) {
      counts.set(workspace.type, (counts.get(workspace.type) ?? 0) + 1);
    }
    return counts;
  }, [workspaces]);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredWorkspaces = useMemo(
    () =>
      sortedWorkspaces.filter((workspace) => {
        if (!normalizedQuery) return true;
        return [workspace.name, workspace.description, workspace.discipline]
          .filter(Boolean)
          .some((value) =>
            String(value).toLowerCase().includes(normalizedQuery)
          );
      }),
    [sortedWorkspaces, normalizedQuery]
  );

  const openWorkspace = (workspaceId: string) => {
    router.push(`/workspaces/${workspaceId}`);
  };

  const openCreateModal = (type?: WorkspaceType) => {
    setShowCreateModal(true);
    if (type) {
      setNewWorkspace((current) => ({ ...current, type }));
    }
  };

  const handleCreateWorkspace = async () => {
    if (!newWorkspace.name.trim()) return;

    try {
      const created = await createWorkspace({
        name: newWorkspace.name,
        type: newWorkspace.type,
        discipline: newWorkspace.discipline || undefined,
        description: newWorkspace.description || undefined,
      });
      setShowCreateModal(false);
      setNewWorkspace({
        name: "",
        type: "sci",
        discipline: "",
        description: "",
      });
      router.push(`/workspaces/${created.id}?onboarding=true`);
    } catch {
      // Store already surfaces the error.
    }
  };

  const handleDeleteWorkspace = async (id: string) => {
    if (confirm("确定要删除此工作空间吗？")) {
      await removeWorkspace(id);
    }
  };

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--wjn-bg-base)]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--wjn-blue)]" />
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--wjn-bg-base)]">
      <Header />

      <main className="wjn-shell-bg relative min-h-screen px-4 pb-24 pt-24 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1160px]">
          {/* header */}
          <div className="flex flex-col gap-6 pt-8 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="h-px w-7 bg-[var(--wjn-review)]" />
                <span className="text-[10.5px] font-semibold tracking-[0.3em] text-[var(--wjn-review)]">
                  我的研究 · RESEARCH PATHS
                </span>
              </div>
              <h1
                className="mt-4 text-[40px] font-bold leading-tight text-[var(--wjn-text)]"
                style={{ fontFamily: serif }}
              >
                工作路径
                <span className="ml-4 align-middle text-[15px] font-normal italic text-[var(--wjn-text-muted)]">
                  {sortedWorkspaces.length} 个活跃的研究工作空间
                </span>
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 items-center gap-2 rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 text-[12.5px] text-[var(--wjn-text-muted)]"
              >
                <Search className="h-3.5 w-3.5" aria-hidden="true" />
                <input
                  type="text"
                  placeholder="搜索工作空间、任务或研究方向…"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className="w-[210px] bg-transparent text-[var(--wjn-text)] outline-none placeholder:text-[var(--wjn-text-muted)]"
                />
              </div>
              <Button
                type="button"
                onClick={() => openCreateModal()}
                className="h-10 rounded-full bg-[var(--wjn-blue)] px-4 text-[12.5px] font-medium text-[#f5f1e8] hover:bg-[var(--wjn-blue-strong)]"
              >
                <Plus className="mr-1.5 h-4 w-4" strokeWidth={2.4} />
                新建工作空间
              </Button>
            </div>
          </div>

          {error ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-6 flex items-center justify-between gap-4 rounded-[var(--wjn-radius-lg)] border border-[rgba(179,52,62,0.24)] bg-[var(--wjn-error-soft)] px-5 py-4 text-[var(--wjn-error)]"
            >
              <span>{error}</span>
              <button onClick={clearError} className="text-sm hover:underline">
                关闭
              </button>
            </motion.div>
          ) : null}

          {/* type chips */}
          <div className="mt-7 flex flex-wrap items-center gap-2.5">
            {workspaceTypes.map((type) => {
              const Icon = workspaceTypeIcons[type.value];
              const count = typeCounts.get(type.value) ?? 0;
              return (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => openCreateModal(type.value)}
                  className="group flex h-10 items-center gap-2 rounded-full border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 text-[12.5px] text-[var(--wjn-text-secondary)] transition-all hover:-translate-y-px hover:shadow-[var(--wjn-shadow-md)]"
                >
                  <Icon className="h-3.5 w-3.5 text-[var(--wjn-blue)]" aria-hidden="true" />
                  <span className="text-[var(--wjn-text)]">{type.label}</span>
                  {count > 0 ? (
                    <span className="rounded-full bg-[var(--wjn-accent-soft)] px-1.5 text-[10.5px] font-semibold text-[var(--wjn-blue)]">
                      {count}
                    </span>
                  ) : null}
                  <Plus className="h-3 w-3 opacity-40 transition-opacity group-hover:opacity-80" />
                </button>
              );
            })}
          </div>

          {/* cards */}
          {!isWorkspacesLoading && filteredWorkspaces.length === 0 ? (
            <section className="mt-10 rounded-[16px] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-12 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-[14px] bg-[var(--wjn-accent-soft)]">
                <Search className="h-6 w-6 text-[var(--wjn-blue)]" />
              </div>
              <h3
                className="mt-5 text-[20px] font-bold text-[var(--wjn-text)]"
                style={{ fontFamily: serif }}
              >
                还没有开始工作路径
              </h3>
              <p className="mx-auto mt-3 max-w-xl text-[13px] leading-[1.85] text-[var(--wjn-text-secondary)]">
                {searchQuery
                  ? "尝试其他搜索词"
                  : "创建第一个工作空间，从调研、结构设计或草稿生成开始。"}
              </p>
            </section>
          ) : (
            <div className="mt-8 grid gap-4">
              <AnimatePresence>
                {filteredWorkspaces.map((workspace) => (
                  <WorkspaceRouteCard
                    key={workspace.id}
                    workspace={workspace}
                    typeLabel={workspaceTypeLabels[workspace.type]}
                    targetOutput={workspaceTargetOutputs[workspace.type]}
                    nextAction={workspaceNextSteps[workspace.type]}
                    onOpen={() => openWorkspace(workspace.id)}
                    onDelete={() => void handleDeleteWorkspace(workspace.id)}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}

          {/* bottom hint */}
          <div className="mt-10 flex items-center justify-between rounded-[16px] border border-dashed border-[var(--wjn-line-strong)] px-6 py-5">
            <div className="text-[13px] text-[var(--wjn-text-secondary)]">
              不确定从哪开始？从一个模板或一句研究问题开始，剩下的交给研究团队。
            </div>
            <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--wjn-blue)]">
              浏览研究模板 <ArrowRight className="h-3.5 w-3.5" />
            </span>
          </div>
        </div>

        <AnimatePresence>
          {showCreateModal ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
              onClick={() => setShowCreateModal(false)}
            >
              <motion.div
                initial={{ scale: 0.96, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.96, opacity: 0 }}
                onClick={(event) => event.stopPropagation()}
                className="w-full max-w-3xl"
              >
                <div className="rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] p-8 shadow-[var(--wjn-shadow-lg)]">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wjn-blue)]">
                        问津 / Wenjin
                      </p>
                      <h2
                        className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--wjn-text)]"
                        style={{ fontFamily: serif }}
                      >
                        创建新工作空间
                      </h2>
                    </div>
                  </div>

                  <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div className="md:col-span-2">
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        工作空间名称
                      </label>
                      <input
                        type="text"
                        value={newWorkspace.name}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            name: event.target.value,
                          }))
                        }
                        placeholder="例如：深度学习在NLP中的应用"
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-3.5 text-[var(--wjn-text)] placeholder:text-[var(--wjn-text-muted)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      />
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        项目类型
                      </label>
                      <select
                        value={newWorkspace.type}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            type: event.target.value as WorkspaceType,
                          }))
                        }
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-3.5 text-[var(--wjn-text)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      >
                        {workspaceTypes.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        学科领域
                      </label>
                      <select
                        value={newWorkspace.discipline}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            discipline: event.target.value,
                          }))
                        }
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-3.5 text-[var(--wjn-text)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      >
                        <option value="">
                          选择学科...
                        </option>
                        {disciplines.map((discipline) => (
                          <option key={discipline.value} value={discipline.value}>
                            {discipline.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="md:col-span-2">
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        描述（可选）
                      </label>
                      <textarea
                        value={newWorkspace.description}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            description: event.target.value,
                          }))
                        }
                        rows={4}
                        placeholder="简要描述您的研究..."
                        className="w-full resize-none rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] px-4 py-3.5 text-[var(--wjn-text)] placeholder:text-[var(--wjn-text-muted)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      />
                    </div>
                  </div>

                  <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => setShowCreateModal(false)}
                      className="flex-1 rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] px-6 py-3.5 text-sm font-medium text-[var(--wjn-text-secondary)] transition-colors hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
                    >
                      取消
                    </button>
                    <Button
                      type="button"
                      onClick={handleCreateWorkspace}
                      disabled={!newWorkspace.name.trim() || isWorkspaceMutating}
                      className="h-auto flex-1 rounded-[var(--wjn-radius-md)] px-6 py-3.5 text-sm"
                    >
                      {isWorkspaceMutating ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        "创建工作空间"
                      )}
                    </Button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>
    </div>
  );
}
