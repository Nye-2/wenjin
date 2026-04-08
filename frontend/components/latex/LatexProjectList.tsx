"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { BookOpenText, ChevronRight, FilePlus2 } from "lucide-react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth";
import { useLatexStore } from "@/stores/latex";

export function LatexProjectList() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const {
    projects,
    templates,
    isProjectsLoading,
    error,
    fetchProjects,
    fetchTemplates,
    createProject,
  } = useLatexStore();
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState<string>("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    void fetchProjects();
    void fetchTemplates();
  }, [fetchProjects, fetchTemplates]);

  const handleCreate = async () => {
    const nextName = name.trim();
    if (!nextName) {
      return;
    }
    setIsCreating(true);
    try {
      const created = await createProject({
        name: nextName,
        template_id: templateId || undefined,
      });
      router.push(`/latex/${created.id}`);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <main className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <Header />
      <section className="mx-auto max-w-7xl px-6 pb-16 pt-28">
        <div className="grid gap-8 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="rounded-[1.8rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.9)] p-6 shadow-[0_20px_50px_rgba(19,34,53,0.08)]">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--brand-brass)]">
              Latex Studio
            </p>
            <h1 className="mt-3 font-serif text-3xl leading-tight">
              独立的 LaTeX 项目工作台
            </h1>
            <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
              这里不绑定 workspace。先建立项目，再进入编辑、编译和预览。
            </p>

            <div className="mt-6 space-y-4">
              <div>
                <label className="mb-2 block text-sm font-medium">项目名称</label>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：ACL rebuttal draft"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium">模板</label>
                <select
                  value={templateId}
                  onChange={(event) => setTemplateId(event.target.value)}
                  className="flex h-11 w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 text-sm text-[var(--text-primary)]"
                >
                  <option value="">空白项目</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.label}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                className="w-full"
                onClick={() => void handleCreate()}
                disabled={isCreating || !name.trim()}
              >
                <FilePlus2 className="mr-2 h-4 w-4" />
                {isCreating ? "创建中..." : "创建 LaTeX 项目"}
              </Button>
            </div>
          </div>

          <div>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-muted)]">
                  Projects
                </p>
                <h2 className="mt-2 text-2xl font-semibold">
                  {isProjectsLoading ? "加载中..." : `${projects.length} 个项目`}
                </h2>
              </div>
            </div>

            {error ? (
              <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            ) : null}

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project, index) => (
                <motion.button
                  key={project.id}
                  type="button"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: index * 0.03 }}
                  onClick={() => router.push(`/latex/${project.id}`)}
                  className="group rounded-[1.6rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.94)] p-5 text-left shadow-[0_18px_40px_rgba(19,34,53,0.06)] transition-all hover:-translate-y-1 hover:border-[var(--brand-teal)]/25"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[rgba(46,111,109,0.12)]">
                      <BookOpenText className="h-5 w-5 text-[var(--brand-teal)]" />
                    </div>
                    <ChevronRight className="h-4 w-4 text-[var(--text-muted)] transition-transform group-hover:translate-x-1" />
                  </div>
                  <h3 className="mt-5 line-clamp-2 text-lg font-semibold">
                    {project.name}
                  </h3>
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">
                    主文件：{project.main_file}
                  </p>
                  <p className="mt-4 text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
                    更新于 {new Date(project.updated_at).toLocaleString("zh-CN")}
                  </p>
                </motion.button>
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
