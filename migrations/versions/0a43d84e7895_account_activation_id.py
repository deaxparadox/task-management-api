"""account activation id

Revision ID: 0a43d84e7895
Revises: a2363362fa88
Create Date: 2025-02-07 15:23:49.058755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a43d84e7895'
down_revision: Union[str, None] = 'a2363362fa88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user', sa.Column('account_activation_id', sa.String(length=36), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('user', 'account_activation_id')
    # ### end Alembic commands ###
