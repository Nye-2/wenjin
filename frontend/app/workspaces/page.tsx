"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Search, Filter, Loader2, Trash2 } from "lucide-react";
import { LiquidGlassCard, GradientText } from "@/components/glass";
import { WorkspaceCard } from "@/components/academic";
import { useWorkspaceStore } from "@/lib/store";
import { Workspace } from "@/lib/api";

// Workspace type labels
const WORKSPACE_TYPES = [
  { value: "sci", label: "SCI Paper" },
  { value: "thesis", label: "Graduate Thesis" },
  { value: "proposal", label: "Research Proposal" },
  { value: "grant", label: "Grant Application" },
];

// Discipline options
const DISCIPLINES = [
  { value: "computer_science", label: "Computer Science" },
  { value: "physics", label: "Physics" },
  { value: "biology", label: "Biology" },
  { value: "chemistry", label: "Chemistry" },
  { value: "medicine", label: "Medicine" },
  { value: "engineering", label: "Engineering" },
  { value: "social_science", label: "Social Science" },
  { value: "humanities", label: "Humanities" },
];

export default function WorkspacesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newWorkspace, setNewWorkspace] = useState({
    name: "",
    type: "sci",
    discipline: "",
    description: "",
  });

  const {
    workspaces,
    isLoading,
    error,
    fetchWorkspaces,
    addWorkspace,
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
      await addWorkspace({
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
    if (confirm("Are you sure you want to delete this workspace?")) {
      await removeWorkspace(id);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-gradient)]">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">
            <GradientText>My Workspaces</GradientText>
          </h1>
          <p className="text-[var(--text-secondary)]">
            Manage your academic research projects
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
              Dismiss
            </button>
          </motion.div>
        )}

        {/* Actions Bar */}
        <div className="flex flex-col md:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search workspaces..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-xl bg-white/50 border border-border/50 focus:border-academic-primary focus:ring-2 focus:ring-academic-primary/20 outline-none transition-all"
            />
          </div>

          <div className="flex gap-2">
            <LiquidGlassCard className="p-2">
              <button className="p-2 rounded-lg hover:bg-white/50 transition-colors">
                <Filter className="w-5 h-5" />
              </button>
            </LiquidGlassCard>

            <motion.button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-white bg-gradient-to-r from-academic-primary to-academic-secondary font-medium"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Plus className="w-5 h-5" />
              New Workspace
            </motion.button>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && workspaces.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-academic-primary" />
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
                  type={workspace.type as "sci" | "thesis" | "proposal" | "grant"}
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
                  className="absolute top-2 right-2 p-2 rounded-lg bg-red-500/10 text-red-500 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/20"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Empty State */}
        {!isLoading && filteredWorkspaces.length === 0 && (
          <div className="text-center py-12">
            <LiquidGlassCard className="p-12 max-w-md mx-auto">
              <div className="text-6xl mb-4">📚</div>
              <h3 className="text-xl font-semibold mb-2">No workspaces found</h3>
              <p className="text-[var(--text-secondary)]">
                {searchQuery
                  ? "Try a different search term"
                  : "Create your first workspace to get started"}
              </p>
            </LiquidGlassCard>
          </div>
        )}

        {/* Create Workspace Modal */}
        <AnimatePresence>
          {showCreateModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
              onClick={() => setShowCreateModal(false)}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                onClick={(e) => e.stopPropagation()}
              >
                <LiquidGlassCard className="p-6 w-full max-w-md">
                  <h2 className="text-xl font-bold mb-4">
                    <GradientText>Create New Workspace</GradientText>
                  </h2>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Workspace Name
                      </label>
                      <input
                        type="text"
                        value={newWorkspace.name}
                        onChange={(e) =>
                          setNewWorkspace({ ...newWorkspace, name: e.target.value })
                        }
                        placeholder="e.g., Deep Learning for NLP"
                        className="w-full px-4 py-2 rounded-lg bg-white/50 border border-border/50 focus:border-academic-primary outline-none"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Project Type
                      </label>
                      <select
                        value={newWorkspace.type}
                        onChange={(e) =>
                          setNewWorkspace({ ...newWorkspace, type: e.target.value })
                        }
                        className="w-full px-4 py-2 rounded-lg bg-white/50 border border-border/50 focus:border-academic-primary outline-none"
                      >
                        {WORKSPACE_TYPES.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Discipline
                      </label>
                      <select
                        value={newWorkspace.discipline}
                        onChange={(e) =>
                          setNewWorkspace({
                            ...newWorkspace,
                            discipline: e.target.value,
                          })
                        }
                        className="w-full px-4 py-2 rounded-lg bg-white/50 border border-border/50 focus:border-academic-primary outline-none"
                      >
                        <option value="">Select discipline...</option>
                        {DISCIPLINES.map((disc) => (
                          <option key={disc.value} value={disc.value}>
                            {disc.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Description (optional)
                      </label>
                      <textarea
                        value={newWorkspace.description}
                        onChange={(e) =>
                          setNewWorkspace({
                            ...newWorkspace,
                            description: e.target.value,
                          })
                        }
                        placeholder="Brief description of your research..."
                        rows={3}
                        className="w-full px-4 py-2 rounded-lg bg-white/50 border border-border/50 focus:border-academic-primary outline-none resize-none"
                      />
                    </div>
                  </div>

                  <div className="flex gap-3 mt-6">
                    <button
                      onClick={() => setShowCreateModal(false)}
                      className="flex-1 px-4 py-2 rounded-lg border border-border/50 hover:bg-white/50 transition-colors"
                    >
                      Cancel
                    </button>
                    <motion.button
                      onClick={handleCreateWorkspace}
                      disabled={!newWorkspace.name.trim() || isLoading}
                      className="flex-1 px-4 py-2 rounded-lg text-white bg-gradient-to-r from-academic-primary to-academic-secondary disabled:opacity-50 flex items-center justify-center gap-2"
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        "Create"
                      )}
                    </motion.button>
                  </div>
                </LiquidGlassCard>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
