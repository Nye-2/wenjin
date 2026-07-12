"""complete foreign-key index coverage and remove duplicate indexes

Revision ID: 095_database_physical_integrity
Revises: 094_workspace_override_cleanup
"""

import sqlalchemy as sa

from alembic import op

revision = "095_database_physical_integrity"
down_revision = "094_workspace_override_cleanup"
branch_labels = None
depends_on = None


_REQUIRED_FOREIGN_KEY_INDEXES = (
    ("ix_credit_redemptions_user_id", "credit_redemptions", "user_id"),
    ("ix_referrals_referrer_user_id", "referrals", "referrer_user_id"),
    ("ix_sandbox_artifacts_environment_id", "sandbox_artifacts", "sandbox_environment_id"),
    ("ix_sandbox_artifacts_workspace_asset_id", "sandbox_artifacts", "workspace_asset_id"),
    ("ix_source_assets_workspace_asset_id", "source_assets", "workspace_asset_id"),
    ("ix_source_outline_nodes_workspace_id", "source_outline_nodes", "workspace_id"),
    ("ix_source_text_units_workspace_id", "source_text_units", "workspace_id"),
    ("ix_thread_messages_user_id", "thread_messages", "user_id"),
    ("ix_tool_invocations_message_id", "tool_invocation_records", "message_id"),
    ("ix_tool_results_message_id", "tool_result_records", "message_id"),
)

_NULLABLE_FOREIGN_KEY_INDEXES = (
    ("ix_artifacts_parent_id", "artifacts", "parent_artifact_id"),
    ("ix_credit_grant_rules_admin_id", "credit_grant_rules", "created_by_admin_id"),
    ("ix_credit_redeem_codes_admin_id", "credit_redeem_codes", "created_by_admin_id"),
    ("ix_credit_redemptions_transaction_id", "credit_redemptions", "transaction_id"),
    ("ix_decisions_superseded_by", "decisions", "superseded_by"),
    ("ix_decisions_source_mission_id", "decisions", "source_mission_id"),
    ("ix_documents_v2_parent_id", "documents_v2", "parent_id"),
    ("ix_mission_runs_parent_id", "mission_runs", "parent_mission_id"),
    ("ix_prism_file_versions_content_asset_id", "prism_file_versions", "content_asset_id"),
    ("ix_prism_renders_mission_id", "prism_renders", "mission_id"),
    ("ix_prism_renders_log_asset_id", "prism_renders", "log_asset_id"),
    ("ix_prism_renders_output_asset_id", "prism_renders", "output_asset_id"),
    ("ix_provenance_links_mission_id", "provenance_links", "mission_id"),
    ("ix_provenance_links_source_anchor_id", "provenance_links", "source_anchor_id"),
    ("ix_sandbox_jobs_stderr_asset_id", "sandbox_job_records", "stderr_asset_id"),
    ("ix_sandbox_jobs_stdout_asset_id", "sandbox_job_records", "stdout_asset_id"),
    ("ix_sandbox_leases_holder_mission_id", "sandbox_leases", "holder_mission_id"),
    ("ix_sandbox_leases_environment_id", "sandbox_leases", "sandbox_environment_id"),
    ("ix_sources_ingest_mission_id", "sources", "ingest_mission_id"),
    ("ix_memory_documents_source_mission_id", "workspace_memory_documents", "source_mission_id"),
    (
        "ix_memory_documents_source_commit_id",
        "workspace_memory_documents",
        "source_mission_commit_id",
    ),
    ("ix_memory_revisions_source_mission_id", "workspace_memory_revisions", "source_mission_id"),
    ("ix_workspace_tasks_source_mission_id", "workspace_tasks", "source_mission_id"),
)

_REDUNDANT_INDEXES = (
    ("ix_model_catalog_entries_model_id", "model_catalog_entries"),
    ("ix_pricing_policies_policy_key", "pricing_policies"),
    ("ix_thread_messages_thread_sequence", "thread_messages"),
    ("ix_users_email", "users"),
)


def upgrade() -> None:
    for name, table, column in _REQUIRED_FOREIGN_KEY_INDEXES:
        op.create_index(name, table, [column])
    for name, table, column in _NULLABLE_FOREIGN_KEY_INDEXES:
        op.create_index(name, table, [column], postgresql_where=sa.text(f"{column} IS NOT NULL"))
    for name, table in _REDUNDANT_INDEXES:
        op.drop_index(name, table_name=table)


def downgrade() -> None:
    raise RuntimeError("095 is an irreversible development cutover; reseed instead")
