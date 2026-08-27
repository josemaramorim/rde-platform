"""
Consolidated configuration settings for the RDE Platform.
Uses pydantic-settings to load variables from environment variables and .env file.
Validates all critical settings on startup.

SECRETS MANAGEMENT:
- Development: Loads from .env file
- Production: Loads from AWS Secrets Manager or HashiCorp Vault
- Set SECRETS_PROVIDER=aws or SECRETS_PROVIDER=vault to enable
"""
from __future__ import annotations

import os
import logging
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Determine the profile to load. Default to standard '.env' if not specified.
profile = os.environ.get("RDE_PROFILE")
env_file = f".env.{profile}" if profile else ".env"

if not os.path.exists(env_file):
    logger.warning(f"Arquivo de ambiente '{env_file}' não encontrado. Usando variáveis de sistema.")

# Initialize secrets manager if configured
_secrets_manager = None
_secrets_provider_type = os.environ.get("SECRETS_PROVIDER", "").lower()

if _secrets_provider_type in ("aws", "vault"):
    try:
        from src.core.secrets_manager import SecretsManager
        
        if _secrets_provider_type == "aws":
            region = os.environ.get("AWS_REGION", "us-east-1")
            _secrets_manager = SecretsManager.initialize(provider_type="aws", region=region)
        elif _secrets_provider_type == "vault":
            vault_addr = os.environ.get("VAULT_ADDR")
            vault_token = os.environ.get("VAULT_TOKEN")
            vault_role = os.environ.get("VAULT_ROLE")
            vault_jwt = os.environ.get("VAULT_JWT")
            
            _secrets_manager = SecretsManager.initialize(
                provider_type="vault",
                vault_addr=vault_addr,
                vault_token=vault_token,
                vault_role=vault_role,
                vault_jwt=vault_jwt,
            )
        
        logger.info(f"🔐 Secrets Manager initialized: {_secrets_provider_type.upper()}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize secrets manager: {e}")
        if os.environ.get("ENVIRONMENT") == "production":
            raise


class Settings(BaseSettings):
    """
    Centralized Application settings loaded from environment variables and .env file.
    All critical settings are validated on startup.
    """
    model_config = SettingsConfigDict(
        env_file=env_file,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ==================== APPLICATION ====================
    APP_NAME: str = Field(default="RDE Platform", description="Application name")
    ENVIRONMENT: str = Field(default="development", description="Environment: development, staging, production")
    DEBUG: bool = Field(default=False, description="Debug mode")
    RDE_PROFILE: Optional[str] = Field(default=None, description="Profile: admin or client")

    # ==================== DATABASE ====================
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./rde_local.db",
        description="Database connection URL - use PostgreSQL in production"
    )

    # ==================== SECURITY ====================
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        min_length=32,
        description="Secret key for JWT signing - generate with secrets.token_urlsafe(32)"
    )
    JWT_SECRET_KEY: str = Field(
        default="your-jwt-secret-key-change-in-production",
        min_length=32,
        description="JWT secret key - can be same as SECRET_KEY"
    )
    ENCRYPTION_KEY: str = Field(
        default="your-encryption-key-32-bytes-change-in-production",
        min_length=32,
        description="AES-256 encryption key for sensitive data (32 bytes hex)"
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, description="JWT token expiration (7 days)")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, description="Refresh token expiration")

    # ==================== MESSAGE BROKER ====================
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1", description="Celery result backend")

    # ==================== STRIPE ====================
    STRIPE_SECRET_KEY: str = Field(default="", description="Stripe secret key - required for payments")
    STRIPE_PUBLIC_KEY: str = Field(default="", description="Stripe public key")
    STRIPE_WEBHOOK_SECRET: str = Field(default="", description="Stripe webhook secret for payment events")
    STRIPE_PRICE_PRO: str = Field(default="", description="Stripe price ID for PRO plan")
    STRIPE_PRICE_VIP: str = Field(default="", description="Stripe price ID for VIP plan")

    # ==================== EMAIL ====================
    MAIL_USERNAME: str = Field(default="noreply@example.com", description="SMTP username")
    MAIL_PASSWORD: str = Field(default="", description="SMTP password or app-specific password")
    MAIL_FROM: str = Field(default="noreply@example.com", description="Email from address")
    MAIL_FROM_NAME: str = Field(default="RDE Platform", description="Email from name")
    MAIL_PORT: int = Field(default=587, description="SMTP port (587 for TLS)")
    MAIL_SERVER: str = Field(default="smtp.gmail.com", description="SMTP server address")

    # ==================== FRONTEND URLs ====================
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend URL - must be HTTPS in production"
    )
    ADMIN_FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Admin frontend URL"
    )
    NEXT_PUBLIC_API_URL: str = Field(
        default="http://localhost:8000",
        description="API URL for frontend - must be HTTPS in production"
    )

    # ==================== CORS ====================
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:3001",
        description="Comma-separated list of allowed origins (no wildcards)"
    )

    # ==================== CLIENT MODE ====================
    ADMIN_SERVER_URL: Optional[str] = Field(
        default=None,
        description="URL do servidor admin para validação de licença (ex: https://admin-server.com). Usado quando RDE_PROFILE=client"
    )

    # ==================== FUSO HORÁRIO / TIMEZONE ====================
    TIMEZONE: str = Field(default="America/Sao_Paulo", description="Fuso horário do servidor (padrão São Paulo UTC-3)")

    # ==================== LOGGING ====================
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # ==================== RATE LIMITING ====================
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Max requests per period")
    RATE_LIMIT_PERIOD: int = Field(default=60, description="Rate limit period in seconds")

    # ==================== AI ENGINE ====================
    AI_USE_ML_MODELS: bool = Field(default=True, description="Enable ML models for detection")

    # ==================== TELEGRAM ====================
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram bot token")
    TELEGRAM_CHAT_ID: str = Field(default="", description="Telegram group chat ID")
    TELEGRAM_GROUP_NAME: str = Field(default="", description="Telegram group name")
    TELEGRAM_API_ID: int = Field(default=24906269, description="Telegram API ID")
    TELEGRAM_API_HASH: str = Field(default="4826f9dd0be48b617f94fc04b88ffabc", description="Telegram API Hash")
    TELEGRAM_PHONE: str = Field(default="", description="Phone number for Telethon auth (+5511999999999)")

    # ==================== ADMIN ====================
    ADMIN_EMAIL: str = Field(default="admin@rde-platform.com", description="Admin email for magic login")

    # ==================== EXTERNAL BROKERS ====================
    # Removido DERIV_APP_ID
    IQOPTION_API_URL: str = Field(default="wss://iqoption.com/echo/websocket", description="IQ Option WebSocket URL")

    # ==================== VALIDATORS ====================

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment variable."""
        if v not in ["development", "staging", "production"]:
            raise ValueError(f"ENVIRONMENT must be one of: development, staging, production. Got {v}")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production":
            if "change-in-production" in v.lower() or "change_in_production" in v.lower():
                raise ValueError("❌ SECRET_KEY não foi alterado! Use um valor seguro gerado com secrets.token_urlsafe(32)")
            if len(v) < 32:
                raise ValueError("❌ SECRET_KEY deve ter pelo menos 32 caracteres")
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str, info) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production":
            if "change-in-production" in v.lower() or "change_in_production" in v.lower():
                raise ValueError("❌ ENCRYPTION_KEY não foi alterado! Use um valor seguro")
            if len(v) < 32:
                raise ValueError("❌ ENCRYPTION_KEY deve ter pelo menos 32 caracteres")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate DATABASE_URL format."""
        if not v:
            raise ValueError("❌ DATABASE_URL é obrigatória")
        return v

    @field_validator("FRONTEND_URL", "ADMIN_FRONTEND_URL", "NEXT_PUBLIC_API_URL")
    @classmethod
    def validate_urls_https_in_production(cls, v: str, info) -> str:
        """Validate URLs use HTTPS in production. Skip for localhost/dev setups."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production":
            if not v or "localhost" in v or "127.0.0.1" in v:
                return v
            if not v.startswith("https://"):
                raise ValueError(f"❌ URLs devem usar HTTPS em produção: {v}")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_allowed_origins(cls, v: str) -> str:
        """Validate ALLOWED_ORIGINS doesn't contain wildcards."""
        if "*" in v:
            raise ValueError("❌ ALLOWED_ORIGINS não pode usar '*'. Use whitelist explícita")
        return v

    def __init__(self, **data):
        """Initialize settings and perform production validations."""
        # If secrets manager is initialized, load secrets from it
        if _secrets_manager:
            self._load_secrets_from_manager(data)
        
        super().__init__(**data)

        # Fallback: load ADMIN_SERVER_URL from saved config file (client setup)
        if not self.ADMIN_SERVER_URL or "SEU_IP" in (self.ADMIN_SERVER_URL or "").upper():
            try:
                from src.routes.client_setup import get_saved_admin_url
                saved = get_saved_admin_url()
                if saved and "SEU_IP" not in saved.upper():
                    self.ADMIN_SERVER_URL = saved
                    logger.info(f"✅ ADMIN_SERVER_URL carregado da config: {saved}")
            except Exception:
                pass
        
        # Production validations
        if self.ENVIRONMENT == "production":
            is_local = (
                "localhost" in str(getattr(self, "FRONTEND_URL", ""))
                or "127.0.0.1" in str(getattr(self, "FRONTEND_URL", ""))
            )
            if is_local:
                logger.info("✅ Modo local — validações de produção simplificadas")
            else:
                logger.warning("⚠️ VALIDAÇÕES DE PRODUÇÃO ATIVAS")
                
                if self.DEBUG:
                    raise ValueError("❌ DEBUG não pode ser True em produção")
                
                if not self.STRIPE_SECRET_KEY or "REPLACE" in self.STRIPE_SECRET_KEY:
                    raise ValueError("❌ STRIPE_SECRET_KEY não configurada em produção")
                
                if not self.STRIPE_PRICE_PRO or "REPLACE" in self.STRIPE_PRICE_PRO:
                    raise ValueError("❌ STRIPE_PRICE_PRO não configurada em produção")
                
                if not self.MAIL_PASSWORD:
                    raise ValueError("❌ MAIL_PASSWORD obrigatória em produção")
                
                if "localhost" in self.DATABASE_URL and "sqlite" not in self.DATABASE_URL:
                    raise ValueError("❌ Database localhost não permitido em produção")
                
                logger.info("✅ Todas as validações de produção passaram")

    @staticmethod
    def _load_secrets_from_manager(data: dict):
        """Load secrets from external manager (AWS Secrets Manager or Vault)"""
        if not _secrets_manager:
            return
        
        try:
            # Try to load a secret named after the app environment
            secret_name = os.environ.get("SECRET_NAME", "rde-platform/production")
            logger.info(f"🔐 Loading secrets from: {secret_name}")
            
            secrets = _secrets_manager.get_secret(secret_name)
            
            # Merge secrets into data, respecting existing values (env vars take precedence)
            for key, value in secrets.items():
                if key.upper() not in data:
                    data[key.upper()] = value
                    logger.debug(f"Loaded secret: {key.upper()}")
            
            logger.info(f"✅ Loaded {len(secrets)} secrets from manager")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load secrets from manager: {e}")

    def get_allowed_origins_list(self) -> list[str]:
        """Parse ALLOWED_ORIGINS string into list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


# Instantiate settings (validates on creation)
try:
    settings = Settings()
    logger.info(f"✅ Configurações carregadas (ambiente: {settings.ENVIRONMENT})")
except ValueError as e:
    logger.error(f"❌ Erro ao carregar configurações: {e}")
    raise