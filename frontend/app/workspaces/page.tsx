"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  BookOpen,
  Code2,
  FileText,
  FlaskConical,
  Lightbulb,
  Loader2,
  Plus,
  Search,
  Sigma,
  Trash2,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/i18n-provider";
import { cn } from "@/lib/utils";
import { WORKSPACE_TYPES, type WorkspaceType } from "@/lib/workspace-types";
import { useWorkspaceStore, Workspace } from "@/stores/workspace";
import { useAuthStore } from "@/stores/auth";

const workspaceTypeIcons: Record<WorkspaceType, typeof FileText> = {
  sci: FileText,
  thesis: BookOpen,
  proposal: FlaskConical,
  software_copyright: Code2,
  math_modeling: Sigma,
  patent: Lightbulb,
};

const workspaceTypeAccents: Record<
  WorkspaceType,
  { icon: string; chip: string }
> = {
  sci: {
    icon: "rgba(44, 93, 160, 0.12)",
    chip: "text-[var(--wjn-blue-strong)] bg-[var(--wjn-accent-soft)] border-[var(--wjn-accent-line)]",
  },
  thesis: {
    icon: "rgba(15, 118, 110, 0.12)",
    chip: "text-[var(--wjn-evidence)] bg-[var(--wjn-evidence-soft)] border-[rgba(15,118,110,0.24)]",
  },
  proposal: {
    icon: "rgba(180, 83, 9, 0.12)",
    chip: "text-[var(--wjn-review)] bg-[var(--wjn-review-soft)] border-[rgba(180,83,9,0.24)]",
  },
  software_copyright: {
    icon: "rgba(15, 31, 53, 0.08)",
    chip: "text-[var(--wjn-text-secondary)] bg-[var(--wjn-surface-subtle)] border-[var(--wjn-line)]",
  },
  math_modeling: {
    icon: "rgba(15, 118, 110, 0.12)",
    chip: "text-[var(--wjn-evidence)] bg-[var(--wjn-evidence-soft)] border-[rgba(15,118,110,0.24)]",
  },
  patent: {
    icon: "rgba(231, 176, 8, 0.14)",
    chip: "text-[var(--wjn-review)] bg-[rgba(231,176,8,0.10)] border-[rgba(231,176,8,0.24)]",
  },
};

function formatWorkspaceDate(dateString: string, locale: "cn" | "en") {
  const date = new Date(dateString);
  return date.toLocaleDateString(locale === "cn" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function WorkspaceRouteCard({
  workspace,
  locale,
  typeLabel,
  targetOutput,
  nextAction,
  lastUpdatedLabel,
  targetOutputLabel,
  nextActionLabel,
  continueLabel,
  latestLabel,
  onOpen,
  onDelete,
  featured = false,
}: {
  workspace: Workspace;
  locale: "cn" | "en";
  typeLabel: string;
  targetOutput: string;
  nextAction: string;
  lastUpdatedLabel: string;
  targetOutputLabel: string;
  nextActionLabel: string;
  continueLabel: string;
  latestLabel?: string;
  onOpen: () => void;
  onDelete: () => void;
  featured?: boolean;
}) {
  const Icon = workspaceTypeIcons[workspace.type];
  const accent = workspaceTypeAccents[workspace.type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0.88, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      className="group h-full"
    >
      <div
        className={cn(
          "route-card-hover relative flex h-full flex-col overflow-hidden rounded-[var(--wjn-radius-xl)] p-6",
          featured && "route-card-featured"
        )}
      >
        <div className="absolute right-4 top-4 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            className="rounded-full border border-[rgba(185,28,28,0.22)] bg-white p-2 text-[var(--wjn-error)] transition-colors hover:bg-[var(--wjn-error-soft)]"
            aria-label="Delete workspace"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>

        <button
          type="button"
          onClick={onOpen}
          className="flex h-full flex-col text-left"
        >
          <div className="flex items-start justify-between gap-3">
            <div
              className="flex h-12 w-12 items-center justify-center rounded-[var(--wjn-radius-lg)]"
              style={{ background: accent.icon }}
            >
              <Icon className="h-5 w-5 text-[var(--wjn-text)]" />
            </div>
            <span
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                accent.chip
              )}
            >
              {typeLabel}
            </span>
          </div>

          <div className="mt-5">
            {latestLabel ? (
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wjn-review)]">
                {latestLabel}
              </p>
            ) : null}
            <h3 className="mt-2 line-clamp-2 text-xl font-semibold tracking-[-0.015em] text-[var(--wjn-text)]">
              {workspace.name}
            </h3>
            <p className="mt-3 line-clamp-2 min-h-[3.5rem] text-sm leading-7 text-[var(--wjn-text-secondary)]">
              {workspace.description?.trim() ||
                workspace.discipline ||
                targetOutput}
            </p>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <div className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--wjn-text-muted)]">
                {lastUpdatedLabel}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--wjn-text)]">
                {formatWorkspaceDate(workspace.updated_at, locale)}
              </p>
            </div>
            <div className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--wjn-text-muted)]">
                {targetOutputLabel}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--wjn-text)]">
                {targetOutput}
              </p>
            </div>
          </div>

          <div className="mt-4 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] p-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--wjn-text-muted)]">
              {nextActionLabel}
            </p>
            <p className="mt-2 text-sm leading-7 text-[var(--wjn-text-secondary)]">
              {nextAction}
            </p>
          </div>

          <div className="mt-6 flex items-center justify-between text-sm font-medium text-[var(--wjn-blue)]">
            <span>{continueLabel}</span>
            <ArrowRight className="h-4 w-4" />
          </div>
        </button>
      </div>
    </motion.div>
  );
}

export default function WorkspacesPage() {
  const router = useRouter();
  const { t, locale } = useI18n();
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

  const workspaceTypes = useMemo(
    () =>
      WORKSPACE_TYPES.map((value) => ({
        value,
        label: t(`workspace.types.${value}`),
      })),
    [t]
  );

  const disciplines = useMemo(
    () => [
      { value: "computer_science", label: t("workspace.disciplines.computer_science") },
      { value: "physics", label: t("workspace.disciplines.physics") },
      { value: "biology", label: t("workspace.disciplines.biology") },
      { value: "chemistry", label: t("workspace.disciplines.chemistry") },
      { value: "medicine", label: t("workspace.disciplines.medicine") },
      { value: "engineering", label: t("workspace.disciplines.engineering") },
      { value: "social_science", label: t("workspace.disciplines.social_science") },
      { value: "humanities", label: t("workspace.disciplines.humanities") },
    ],
    [t]
  );

  const sortedWorkspaces = useMemo(
    () =>
      [...workspaces].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      ),
    [workspaces]
  );

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
    if (confirm(t("workspace.deleteConfirm"))) {
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

      <main className="wjn-shell-bg relative overflow-hidden px-4 pb-16 pt-24 sm:px-6 lg:px-8">
        <div className="pointer-events-none absolute inset-x-0 top-20 h-px bg-[var(--wjn-line)]" />
        <div className="relative mx-auto max-w-7xl space-y-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-3xl font-semibold tracking-[-0.025em] text-[var(--wjn-text)]">
                {t("workspace.title")}
              </h1>
              <span className="rounded-full border border-[var(--wjn-line)] bg-white px-3 py-1 text-sm text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)]">
                {sortedWorkspaces.length}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative min-w-[240px]">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--wjn-text-muted)]" />
                <input
                  type="text"
                  placeholder={t("workspace.searchPlaceholder")}
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white py-2.5 pl-11 pr-4 text-sm text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)] placeholder:text-[var(--wjn-text-muted)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                />
              </div>
              <Button
                type="button"
                onClick={() => openCreateModal()}
                className="rounded-xl px-5 py-2.5 text-sm"
              >
                <Plus className="mr-2 h-4 w-4" />
                {t("workspace.newWorkspace")}
              </Button>
            </div>
          </div>

          {error ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between gap-4 rounded-[var(--wjn-radius-lg)] border border-[rgba(185,28,28,0.24)] bg-[var(--wjn-error-soft)] px-5 py-4 text-[var(--wjn-error)]"
            >
              <span>{error}</span>
              <button onClick={clearError} className="text-sm hover:underline">
                {t("common.dismiss")}
              </button>
            </motion.div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {workspaceTypes.map((type) => {
              const Icon = workspaceTypeIcons[type.value];
              return (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => openCreateModal(type.value)}
                  className="inline-flex items-center gap-2 rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:bg-[var(--wjn-surface-subtle)]"
                >
                  <Icon className="h-4 w-4 text-[var(--wjn-text-secondary)]" />
                  {type.label}
                  <Plus className="h-3.5 w-3.5 text-[var(--wjn-text-muted)]" />
                </button>
              );
            })}
          </div>

          {!isWorkspacesLoading && filteredWorkspaces.length === 0 ? (
            <section className="rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-white p-10 text-center shadow-[var(--wjn-shadow-md)]">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[var(--wjn-radius-xl)] bg-[var(--wjn-accent-soft)]">
                <Search className="h-7 w-7 text-[var(--wjn-blue)]" />
              </div>
              <h3 className="mt-5 text-xl font-semibold text-[var(--wjn-text)]">
                {t("workspace.empty.title")}
              </h3>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-[var(--wjn-text-secondary)]">
                {searchQuery
                  ? t("workspace.empty.searchHint")
                  : t("workspace.empty.description")}
              </p>
            </section>
          ) : (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
              <AnimatePresence>
                {filteredWorkspaces.map((workspace, index) => (
                  <WorkspaceRouteCard
                    key={workspace.id}
                    workspace={workspace}
                    locale={locale}
                    typeLabel={t(`workspace.types.${workspace.type}`)}
                    targetOutput={t(`workspace.targets.${workspace.type}`)}
                    nextAction={t(`workspace.nextSteps.${workspace.type}`)}
                    lastUpdatedLabel={t("workspace.cards.lastUpdated")}
                    targetOutputLabel={t("workspace.cards.targetOutput")}
                    nextActionLabel={t("workspace.cards.nextAction")}
                    continueLabel={t("workspace.cards.open")}
                    featured={index === 0 && !normalizedQuery}
                    latestLabel={index === 0 && !normalizedQuery ? t("workspace.cards.latest") : undefined}
                    onOpen={() => openWorkspace(workspace.id)}
                    onDelete={() => void handleDeleteWorkspace(workspace.id)}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}
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
                <div className="rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-white p-8 shadow-[var(--wjn-shadow-lg)]">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--wjn-blue)]">
                        {t("brand.cn")} / {t("brand.en")}
                      </p>
                      <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em] text-[var(--wjn-text)]">
                        {t("workspace.createModal.title")}
                      </h2>
                    </div>
                  </div>

                  <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div className="md:col-span-2">
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        {t("workspace.createModal.name")}
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
                        placeholder={t("workspace.createModal.namePlaceholder")}
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white px-4 py-3.5 text-[var(--wjn-text)] placeholder:text-[var(--wjn-text-muted)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      />
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-medium text-[var(--wjn-text)]">
                        {t("workspace.createModal.type")}
                      </label>
                      <select
                        value={newWorkspace.type}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            type: event.target.value as WorkspaceType,
                          }))
                        }
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white px-4 py-3.5 text-[var(--wjn-text)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
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
                        {t("workspace.createModal.discipline")}
                      </label>
                      <select
                        value={newWorkspace.discipline}
                        onChange={(event) =>
                          setNewWorkspace((current) => ({
                            ...current,
                            discipline: event.target.value,
                          }))
                        }
                        className="w-full rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white px-4 py-3.5 text-[var(--wjn-text)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      >
                        <option value="">
                          {t("workspace.createModal.disciplinePlaceholder")}
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
                        {t("workspace.createModal.description")}
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
                        placeholder={t("workspace.createModal.descriptionPlaceholder")}
                        className="w-full resize-none rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] bg-white px-4 py-3.5 text-[var(--wjn-text)] placeholder:text-[var(--wjn-text-muted)] focus:border-[var(--wjn-blue)] focus:outline-none focus:ring-2 focus:ring-[var(--wjn-accent-soft)]"
                      />
                    </div>
                  </div>

                  <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => setShowCreateModal(false)}
                      className="flex-1 rounded-[var(--wjn-radius-md)] border border-[var(--wjn-line)] px-6 py-3.5 text-sm font-medium text-[var(--wjn-text-secondary)] transition-colors hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]"
                    >
                      {t("common.cancel")}
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
                        t("workspace.createModal.createButton")
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
