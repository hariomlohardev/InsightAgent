"""001_init — datasets, dashboards, users, workspaces, billing, audit

Revision ID: 001_init
Revises: 
Create Date: 2025-08-08

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # datasets — matches storage.save_dataset JSON shape
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), index=True, nullable=False, server_default="default"),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("columns", sa.Integer(), nullable=True),
        sa.Column("column_names", sa.JSON(), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
    )
    # dashboards
    op.create_table(
        "dashboards",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), index=True, nullable=False, server_default="default"),
        sa.Column("dataset_id", sa.String(), index=True, nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("widgets", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), unique=True, index=True, nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), index=True, nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    # workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("tier", sa.String(), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    # billing
    op.create_table(
        "billing",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), index=True, nullable=False),
        sa.Column("datasets_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), index=True, nullable=False, server_default="default"),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=True),
    )

def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("billing")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.drop_table("dashboards")
    op.drop_table("datasets")
