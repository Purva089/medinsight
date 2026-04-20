"""Drop old unique constraint and add new one based on report_id

Revision ID: fix_unique_constraint
Revises: a3b4c5d6e7f8
Create Date: 2026-04-19 19:05:00

"""
from alembic import op

# revision identifiers
revision = 'fix_unique_constraint'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint that prevents same test name per patient per day
    op.drop_constraint('uq_lab_result_per_day', 'lab_results', type_='unique')
    
    # Add new constraint: same test name can't appear twice in same report
    op.create_unique_constraint(
        'uq_lab_result_per_report',
        'lab_results',
        ['report_id', 'test_name']
    )


def downgrade() -> None:
    op.drop_constraint('uq_lab_result_per_report', 'lab_results', type_='unique')
    op.create_unique_constraint(
        'uq_lab_result_per_day',
        'lab_results',
        ['patient_id', 'test_name', 'report_date']
    )
