"""Add unique constraint on targets(scan_id, target_type, value)

Revision ID: 002_unique_target
Revises: 001_initial
Create Date: 2026-03-10

Without this constraint, duplicate target rows could be inserted when
theHarvester and Amass discover the same host with different casing,
causing scalar_one_or_none() to raise MultipleResultsFound during
phase 2 enrichment.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_unique_target"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any existing duplicates before adding the constraint.
    # Keep the row with the lowest id for each (scan_id, target_type, value) group.
    op.execute("""
        DELETE FROM targets
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM targets
            GROUP BY scan_id, target_type, value
        )
    """)
    op.create_unique_constraint(
        "uq_targets_scan_type_value",
        "targets",
        ["scan_id", "target_type", "value"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_targets_scan_type_value", "targets", type_="unique")
