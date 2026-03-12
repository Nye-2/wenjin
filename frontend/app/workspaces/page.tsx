"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Search, Filter, Loader2, Trash2 } from "lucide-react";
import { WorkspaceCard } from "@/components/academic";
import { Header } from "@/components/layout/header";
import { useI18n } from "@/components/i18n-provider";
import { useWorkspaceStore, Workspace } from "@/stores/workspace";
import { useAuthStore } from "@/stores/auth";

export default function WorkspacesPage() {
  const router = useRouter();
  const { t } = useI18n();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newWorkspace, setNewWorkspace] = useState({
    name: "",
    type: "sci",
    discipline: "",
    description: "",
  });

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, authLoading, router]);

  // Show loading while checking authentication
  if (authLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
      </main>
    );
  }

  // Workspace type labels (translated)
  const WORKSPACE_TYPES = [
    { value: "sci", label: t("workspace.types.sci") },
    { value: "thesis", label: t("workspace.types.thesis") },
    { value: "proposal", label: t("workspace.types.proposal") },
    { value: "software_copyright", label: t("workspace.types.software_copyright") },
    { value: "patent", label: t("workspace.types.patent") },
  ];

  // Discipline options (translated)
  const DISCIPLINES = [
    { value: "computer_science", label: t("workspace.disciplines.computer_science") },
    { value: "physics", label: t("workspace.disciplines.physics") },
    { value: "biology", label: t("workspace.disciplines.biology") },
    { value: "chemistry", label: t("workspace.disciplines.chemistry") },
    { value: "medicine", label: t("workspace.disciplines.medicine") },
    { value: "engineering", label: t("workspace.disciplines.engineering") },
    { value: "social_science", label: t("workspace.disciplines.social_science") },
    { value: "humanities", label: t("workspace.disciplines.humanities") },
  ];

  const {
    workspaces,
    isWorkspacesLoading,
    isWorkspaceMutating,
    error,
    fetchWorkspaces,
    createWorkspace,
    removeWorkspace,
    clearError,
  } = useWorkspaceStore();

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  const filteredWorkspaces = workspaces.filter((w: Workspace) =>
    w.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleCreateWorkspace = async () => {
    if (!newWorkspace.name.trim()) return;

    try {
      await createWorkspace({
        name: newWorkspace.name,
        type: newWorkspace.type,
        discipline: newWorkspace.discipline || undefined,
        description: newWorkspace.description || undefined,
      });
      setShowCreateModal(false);
      setNewWorkspace({ name: "", type: "sci", discipline: "", description: "" });
    } catch {
      // Error is handled by store
    }
  };

  const handleDeleteWorkspace = async (id: string) => {
    if (confirm(t("workspace.deleteConfirm"))) {
      await removeWorkspace(id);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      {/* Header with Auth */}
      <Header />

      <div className="container mx-auto px-4 py-8 pt-24">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2 text-[var(--text-primary)]">
            {t("workspace.title")}
          </h1>
          <p className="text-[var(--text-secondary)]">
            {t("workspace.subtitle")}
          </p>
        </div>

        {/* Error Banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-600 flex justify-between items-center"
          >
            <span>{error}</span>
            <button onClick={clearError} className="text-sm hover:underline">
              {t("common.dismiss")}
            </button>
          </motion.div>
        )}

        {/* Actions Bar */}
        <div className="flex flex-col md:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder={t("workspace.searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
            />
          </div>

          <div className="flex gap-3">
            <button className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] transition-all">
              <Filter className="w-5 h-5" />
            </button>

            <motion.button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 px-6 py-3.5 rounded-xl text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] font-medium hover:shadow-xl transition-shadow"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Plus className="w-5 h-5" />
              {t("workspace.newWorkspace")}
            </motion.button>
          </div>
        </div>

        {/* Loading State */}
        {isWorkspacesLoading && workspaces.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
          </div>
        )}

        {/* Workspaces Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <AnimatePresence>
            {filteredWorkspaces.map((workspace: Workspace, index: number) => (
              <motion.div
                key={workspace.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ delay: index * 0.05 }}
                className="relative group"
              >
                <WorkspaceCard
                  id={workspace.id}
                  name={workspace.name}
                  type={workspace.type as "sci" | "thesis" | "proposal" | "software_copyright" | "patent"}
                  discipline={workspace.discipline}
                  paperCount={0}
                  artifactCount={0}
                  createdAt={workspace.created_at.split("T")[0]}
                />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteWorkspace(workspace.id);
                  }}
                  className="absolute top-3 right-3 p-2 rounded-lg bg-red-500/10 text-red-500 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/20"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Empty State */}
        {!isWorkspacesLoading && filteredWorkspaces.length === 0 && (
          <div className="text-center py-16">
            <div className="p-12 max-w-md mx-auto bg-[var(--bg-elevated)] rounded-2xl border border-[var(--border-default)]">
              <div className="text-6xl mb-4">📚</div>
              <h3 className="text-xl font-semibold mb-2 text-[var(--text-primary)]">
                {t("workspace.empty.title")}
              </h3>
              <p className="text-[var(--text-secondary)]">
                {searchQuery
                  ? t("workspace.empty.searchHint")
                  : t("workspace.empty.description")}
              </p>
            </div>
          </div>
        )}

        {/* Create Workspace Modal */}
        <AnimatePresence>
          {showCreateModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
              onClick={() => setShowCreateModal(false)}
            >
              <motion.div
                initial={{ scale: 0.95, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.95, opacity: 0 }}
                onClick={(e) => e.stopPropagation()}
                className="w-full max-w-3xl"
              >
                <div className="bg-[var(--bg-elevated)] rounded-2xl border border-[var(--border-default)] shadow-2xl p-8">
                  <h2 className="text-2xl font-bold mb-8 text-[var(--text-primary)]">
                    {t("workspace.createModal.title")}
                  </h2>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Workspace Name - Full width */}
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                        {t("workspace.createModal.name")}
                      </label>
                      <input
                        type="text"
                        value={newWorkspace.name}
                        onChange={(e) =>
                          setNewWorkspace({ ...newWorkspace, name: e.target.value })
                        }
                        placeholder={t("workspace.createModal.namePlaceholder")}
                        className="w-full px-4 py-3.5 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
                      />
                    </div>

                    {/* Project Type */}
                    <div>
                      <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                        {t("workspace.createModal.type")}
                      </label>
                      <select
                        value={newWorkspace.type}
                        onChange={(e) =>
                          setNewWorkspace({ ...newWorkspace, type: e.target.value })
                        }
                        className="w-full px-4 py-3.5 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all cursor-pointer"
                      >
                        {WORKSPACE_TYPES.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Discipline */}
                    <div>
                      <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                        {t("workspace.createModal.discipline")}
                      </label>
                      <select
                        value={newWorkspace.discipline}
                        onChange={(e) =>
                          setNewWorkspace({
                            ...newWorkspace,
                            discipline: e.target.value,
                          })
                        }
                        className="w-full px-4 py-3.5 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all cursor-pointer"
                      >
                        <option value="">
                          {t("workspace.createModal.disciplinePlaceholder")}
                        </option>
                        {DISCIPLINES.map((disc) => (
                          <option key={disc.value} value={disc.value}>
                            {disc.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Description - Full width */}
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium mb-2 text-[var(--text-primary)]">
                        {t("workspace.createModal.description")}
                      </label>
                      <textarea
                        value={newWorkspace.description}
                        onChange={(e) =>
                          setNewWorkspace({
                            ...newWorkspace,
                            description: e.target.value,
                          })
                        }
                        placeholder={t("workspace.createModal.descriptionPlaceholder")}
                        rows={3}
                        className="w-full px-4 py-3.5 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none resize-none transition-all"
                      />
                    </div>
                  </div>

                  <div className="flex gap-4 mt-8">
                    <button
                      onClick={() => setShowCreateModal(false)}
                      className="flex-1 px-6 py-3.5 rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] transition-all font-medium"
                    >
                      {t("common.cancel")}
                    </button>
                    <motion.button
                      onClick={handleCreateWorkspace}
                      disabled={!newWorkspace.name.trim() || isWorkspaceMutating}
                      className="flex-1 px-6 py-3.5 rounded-xl text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#2563EB] hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all font-medium"
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {isWorkspaceMutating ? (
                        <Loader2 className="w-5 h-5 animate-spin" />
                      ) : (
                        t("workspace.createModal.createButton")
                      )}
                    </motion.button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
