"""Add latex core tables.

Revision ID: 017_add_latex_core_tables
Revises: 016_add_workspace_templates
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_add_latex_core_tables"
down_revision: Union[str, None] = "016_add_workspace_templates"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    table_names = _table_names()

    if "latex_projects" not in table_names:
        op.create_table(
            "latex_projects",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("template_id", sa.String(50), nullable=True),
            sa.Column("main_file", sa.String(255), nullable=False, server_default="main.tex"),
            sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("trashed", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("file_order", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("llm_config", postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_latex_projects_user_id", "latex_projects", ["user_id"])
        op.create_index("ix_latex_projects_trashed", "latex_projects", ["trashed"])

    if "latex_templates" not in table_names:
        op.create_table(
            "latex_templates",
            sa.Column("id", sa.String(50), primary_key=True),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("main_file", sa.String(255), nullable=False, server_default="main.tex"),
            sa.Column("category", sa.String(50), nullable=False, server_default="academic"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("description_en", sa.Text, nullable=True),
            sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("author", sa.String(100), nullable=True),
            sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("template_path", sa.String(500), nullable=True),
        )
        templates_table = sa.table(
            "latex_templates",
            sa.column("id", sa.String),
            sa.column("label", sa.String),
            sa.column("main_file", sa.String),
            sa.column("category", sa.String),
            sa.column("description", sa.Text),
            sa.column("description_en", sa.Text),
            sa.column("tags", postgresql.JSONB),
            sa.column("author", sa.String),
            sa.column("featured", sa.Boolean),
            sa.column("template_path", sa.String),
        )
        op.bulk_insert(
            templates_table,
            [
                {
                    "id": "acl",
                    "label": "ACL",
                    "main_file": "main.tex",
                    "category": "academic",
                    "description": "ACL conference template",
                    "description_en": "ACL conference template",
                    "tags": ["ACL", "NLP"],
                    "author": "WenjinPrism",
                    "featured": True,
                    "template_path": "acl",
                },
                {
                    "id": "cvpr",
                    "label": "CVPR",
                    "main_file": "main.tex",
                    "category": "academic",
                    "description": "CVPR conference template",
                    "description_en": "CVPR conference template",
                    "tags": ["CVPR", "Computer Vision"],
                    "author": "WenjinPrism",
                    "featured": True,
                    "template_path": "cvpr",
                },
                {
                    "id": "neurips",
                    "label": "NeurIPS",
                    "main_file": "main.tex",
                    "category": "academic",
                    "description": "NeurIPS conference template",
                    "description_en": "NeurIPS conference template",
                    "tags": ["NeurIPS", "Machine Learning"],
                    "author": "WenjinPrism",
                    "featured": True,
                    "template_path": "neurips",
                },
                {
                    "id": "icml",
                    "label": "ICML",
                    "main_file": "main.tex",
                    "category": "academic",
                    "description": "ICML conference template",
                    "description_en": "ICML conference template",
                    "tags": ["ICML", "Machine Learning"],
                    "author": "WenjinPrism",
                    "featured": True,
                    "template_path": "icml",
                },
            ],
        )

    if "latex_compile_history" not in table_names:
        op.create_table(
            "latex_compile_history",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("latex_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("engine", sa.String(20), nullable=False),
            sa.Column("main_file", sa.String(255), nullable=False),
            sa.Column("status", sa.Integer(), nullable=False),
            sa.Column("log", sa.Text(), nullable=True),
            sa.Column("pdf_path", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_latex_compile_history_project_id", "latex_compile_history", ["project_id"])


def downgrade() -> None:
    table_names = _table_names()
    if "latex_compile_history" in table_names:
        op.drop_index("ix_latex_compile_history_project_id", table_name="latex_compile_history")
        op.drop_table("latex_compile_history")
    if "latex_templates" in table_names:
        op.drop_table("latex_templates")
    if "latex_projects" in table_names:
        op.drop_index("ix_latex_projects_trashed", table_name="latex_projects")
        op.drop_index("ix_latex_projects_user_id", table_name="latex_projects")
        op.drop_table("latex_projects")
