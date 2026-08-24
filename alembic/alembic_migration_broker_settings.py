"""Migration: Add broker_settings tables

Revision ID: 0002_add_broker_settings
Revises: 0001_initial
Create Date: 2024-01-15

"""
from alembic import op # type: ignore
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_broker_settings'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Criar tabela broker_settings
    # Nota: sa.Enum com o parâmetro native_enum=False cria restrições de CHECK válidas para SQLite 
    # e gera tipos ENUM nativos automaticamente caso rode no PostgreSQL.
    op.create_table(
        'broker_settings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('broker_type', sa.Enum('iqoption', 'quotex', 'pocketoption', name='brokertype', native_enum=False), nullable=False),
        sa.Column('broker_name', sa.String(length=50), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('status', sa.Enum('disconnected', 'connecting', 'connected', 'error', 'inactive', name='brokerstatus', native_enum=False), nullable=False, server_default='disconnected'),
        sa.Column('last_connected', sa.DateTime(), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('connection_error', sa.Text(), nullable=True),
        
        # Autenticação
        sa.Column('api_token', sa.String(length=500), nullable=True),
        sa.Column('iq_email', sa.String(length=255), nullable=True),
        sa.Column('iq_password', sa.String(length=255), nullable=True),
        sa.Column('iq_user_id', sa.Integer(), nullable=True),
        sa.Column('quotex_username', sa.String(length=255), nullable=True),
        sa.Column('quotex_api_key', sa.String(length=500), nullable=True),
        sa.Column('po_username', sa.String(length=255), nullable=True),
        sa.Column('po_api_key', sa.String(length=500), nullable=True),
        
        # Configurações de Trade
        sa.Column('default_stake', sa.Float(), nullable=True),
        sa.Column('max_stake', sa.Float(), nullable=True),
        sa.Column('max_gales', sa.Integer(), nullable=True),
        sa.Column('daily_stop_loss', sa.Float(), nullable=True),
        sa.Column('daily_meta', sa.Float(), nullable=True),
        sa.Column('max_cycle_pct', sa.Float(), nullable=True),
        sa.Column('latency_protection', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auto_stop_on_loss', sa.Boolean(), nullable=False, server_default='true'),
        
        # Saldo e Estatísticas
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('balance_updated_at', sa.DateTime(), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_wins', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_losses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_profit', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('today_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('today_profit', sa.Float(), nullable=False, server_default='0.0'),
        
        # Rastreamento
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_broker_settings_user_id', 'user_id'),
        sa.Index('ix_broker_settings_broker_type', 'broker_type'),
        sa.Index('ix_broker_settings_status', 'status'),
    )

    # Criar tabela broker_connections
    op.create_table(
        'broker_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broker_setting_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Enum('disconnected', 'connecting', 'connected', 'error', 'inactive', name='brokerstatus', native_enum=False), nullable=False),
        sa.Column('connected_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('disconnected_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('connection_type', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        
        sa.ForeignKeyConstraint(['broker_setting_id'], ['broker_settings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_broker_connections_broker_setting_id', 'broker_setting_id'),
    )

    # Criar tabela broker_trades
    op.create_table(
        'broker_trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broker_setting_id', sa.Uuid(), nullable=False),
        sa.Column('broker_trade_id', sa.String(length=255), nullable=True),
        sa.Column('asset', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('duration', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('profit_loss', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('result', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('is_martingale', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cycle_step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        
        sa.ForeignKeyConstraint(['broker_setting_id'], ['broker_settings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_broker_trades_broker_setting_id', 'broker_setting_id'),
        sa.Index('ix_broker_trades_asset', 'asset'),
        sa.Index('ix_broker_trades_status', 'status'),
        sa.Index('ix_broker_trades_created_at', 'created_at'),
    )


def downgrade() -> None:
    # Drop tabelas respeitando constraints
    op.drop_table('broker_trades')
    op.drop_table('broker_connections')
    op.drop_table('broker_settings')
    
    # Executa a remoção de tipos enum apenas se estiver conectada a um banco Postgres
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS brokerstatus')
        op.execute('DROP TYPE IF EXISTS brokertype')