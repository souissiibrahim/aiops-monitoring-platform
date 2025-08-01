"""Change recommendations from ARRAY to JSONB

Revision ID: 2db380fd870d
Revises: 1cf389de6007
Create Date: 2025-08-01 11:47:38.939795

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2db380fd870d'
down_revision = '1cf389de6007'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dependency_graph', schema=None) as batch_op:
        batch_op.drop_column('last_updated')

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_incident_root_cause', 'rca_analysis', ['root_cause_id'], ['rca_id'], initially='DEFERRED', deferrable=True, use_alter=True)

    with op.batch_alter_table('models', schema=None) as batch_op:
        batch_op.alter_column('type',
               existing_type=sa.VARCHAR(),
               nullable=False)

    # 🚨 Replace this block with manual 2-step fix
    with op.batch_alter_table('rca_analysis', schema=None) as batch_op:
        # Step 1: Add temporary JSONB column
        batch_op.add_column(sa.Column('recommendations_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Step 2: Migrate values using SQL (outside batch_op)
    op.execute("""
        UPDATE rca_analysis
        SET recommendations_jsonb = to_jsonb(recommendations)
    """)

    with op.batch_alter_table('rca_analysis', schema=None) as batch_op:
        # Step 3: Drop old column
        batch_op.drop_column('recommendations')

        # Step 4: Rename new column
        batch_op.alter_column('recommendations_jsonb', new_column_name='recommendations')

        # Step 5: Create FK on root_cause_node_id
        batch_op.create_foreign_key(None, 'telemetry_sources', ['root_cause_node_id'], ['source_id'])


def downgrade():
    with op.batch_alter_table('rca_analysis', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('recommendations')
        batch_op.add_column(sa.Column('recommendations', postgresql.ARRAY(sa.TEXT()), nullable=True))

    op.execute("""
        UPDATE rca_analysis
        SET recommendations = ARRAY(
            SELECT jsonb_array_elements_text(recommendations_jsonb)
        )
    """)

    with op.batch_alter_table('models', schema=None) as batch_op:
        batch_op.alter_column('type',
               existing_type=sa.VARCHAR(),
               nullable=True)

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_incident_root_cause', type_='foreignkey')

    with op.batch_alter_table('dependency_graph', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_updated', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))

    # ### end Alembic commands ###
