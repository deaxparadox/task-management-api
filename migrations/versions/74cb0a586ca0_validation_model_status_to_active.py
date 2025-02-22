"""validation model status to active

Revision ID: 74cb0a586ca0
Revises: dc0eeec87bef
Create Date: 2025-02-07 16:33:29.188729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '74cb0a586ca0'
down_revision: Union[str, None] = 'dc0eeec87bef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('validation', sa.Column('active', sa.Boolean(), nullable=True))
    op.drop_column('validation', 'status')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('validation', sa.Column('status', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.drop_column('validation', 'active')
    # ### end Alembic commands ###
