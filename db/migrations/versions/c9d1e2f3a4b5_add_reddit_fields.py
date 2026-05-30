"""Add Reddit fields to rescue_posts

Revision ID: c9d1e2f3a4b5
Revises: 8b15e2ecb965
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "8b15e2ecb965"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rescue_posts", sa.Column("subreddit", sa.String(), nullable=True))
    op.add_column("rescue_posts", sa.Column("post_title", sa.Text(), nullable=True))
    op.add_column("rescue_posts", sa.Column("post_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("rescue_posts", "post_url")
    op.drop_column("rescue_posts", "post_title")
    op.drop_column("rescue_posts", "subreddit")
