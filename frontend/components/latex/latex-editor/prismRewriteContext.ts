export const LOCAL_REWRITE_CONTEXT_REQUIREMENTS = {
  include_manuscript_context: true,
  include_workspace_history: false,
  include_related_documents: false,
  include_sandbox_artifacts: false,
  include_pending_review_summary: false,
} as const;

export const DOCUMENT_REWRITE_CONTEXT_REQUIREMENTS = {
  include_manuscript_context: true,
  include_workspace_history: true,
  include_related_documents: true,
  include_sandbox_artifacts: true,
  include_pending_review_summary: true,
} as const;
