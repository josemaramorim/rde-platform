"""
Secrets Manager - Abstraction layer for external secrets management
Supports: AWS Secrets Manager, HashiCorp Vault, Environment Variables (fallback)
"""

import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SecretsProvider(ABC):
    """Abstract base class for secrets providers"""

    @abstractmethod
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Retrieve a secret by name"""
        pass

    @abstractmethod
    def get_secret_value(self, secret_name: str, key: Optional[str] = None) -> str:
        """Retrieve a specific secret value"""
        pass


class AWSSecretsManagerProvider(SecretsProvider):
    """AWS Secrets Manager provider for production deployments"""

    def __init__(self, region: str = "us-east-1"):
        try:
            import boto3
            self.client = boto3.client("secretsmanager", region_name=region)
            logger.info(f"✅ AWS Secrets Manager initialized in region {region}")
        except ImportError:
            logger.error(
                "❌ boto3 not installed. Install with: pip install boto3"
            )
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize AWS Secrets Manager: {e}")
            raise

    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Retrieve entire secret from AWS Secrets Manager"""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            
            if "SecretString" in response:
                return json.loads(response["SecretString"])
            else:
                logger.warning(f"Secret {secret_name} is binary, returning raw value")
                return {"value": response["SecretBinary"]}
                
        except self.client.exceptions.ResourceNotFoundException:
            logger.error(f"❌ Secret '{secret_name}' not found in AWS Secrets Manager")
            raise ValueError(f"Secret '{secret_name}' not found")
        except Exception as e:
            logger.error(f"❌ Error retrieving secret from AWS: {e}")
            raise

    def get_secret_value(self, secret_name: str, key: Optional[str] = None) -> str:
        """Retrieve specific key from secret"""
        secret = self.get_secret(secret_name)
        
        if key:
            if key not in secret:
                raise KeyError(f"Key '{key}' not found in secret '{secret_name}'")
            return str(secret[key])
        
        # If no key specified and secret has 'value' key, return that
        if "value" in secret:
            return str(secret["value"])
        
        raise ValueError(
            f"Cannot extract single value from secret '{secret_name}' without key"
        )


class HashiCorpVaultProvider(SecretsProvider):
    """HashiCorp Vault provider for production deployments"""

    def __init__(
        self,
        vault_addr: str,
        vault_token: Optional[str] = None,
        vault_role: Optional[str] = None,
        vault_jwt: Optional[str] = None,
    ):
        try:
            import hvac
        except ImportError:
            logger.error("❌ hvac not installed. Install with: pip install hvac")
            raise

        self.client = hvac.Client(url=vault_addr)
        
        # Authenticate with Vault
        try:
            if vault_token:
                self.client.token = vault_token
                logger.info("✅ Vault authenticated with token")
            elif vault_role and vault_jwt:
                self.client.auth.jwt.jwt_login(role=vault_role, jwt=vault_jwt)
                logger.info(f"✅ Vault authenticated with JWT role '{vault_role}'")
            else:
                raise ValueError("Either vault_token or (vault_role + vault_jwt) required")
                
        except Exception as e:
            logger.error(f"❌ Failed to authenticate with Vault: {e}")
            raise

    def get_secret(self, secret_path: str) -> Dict[str, Any]:
        """Retrieve entire secret from Vault"""
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=secret_path
            )
            return response["data"]["data"]
            
        except Exception as e:
            logger.error(f"❌ Error retrieving secret from Vault at '{secret_path}': {e}")
            raise

    def get_secret_value(self, secret_path: str, key: Optional[str] = None) -> str:
        """Retrieve specific key from secret"""
        secret = self.get_secret(secret_path)
        
        if key:
            if key not in secret:
                raise KeyError(f"Key '{key}' not found in Vault secret '{secret_path}'")
            return str(secret[key])
        
        if "value" in secret:
            return str(secret["value"])
        
        raise ValueError(
            f"Cannot extract single value from Vault secret '{secret_path}' without key"
        )


class EnvSecretsProvider(SecretsProvider):
    """Environment variables provider (fallback, not recommended for production)"""

    def __init__(self):
        import os
        self.env = os.environ
        logger.warning(
            "⚠️  Using environment variables for secrets. "
            "ONLY for development! Use AWS Secrets Manager or Vault for production."
        )

    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Retrieve secret from environment variables (JSON format)"""
        value = self.env.get(secret_name)
        if not value:
            raise ValueError(f"Environment variable '{secret_name}' not set")
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}

    def get_secret_value(self, secret_name: str, key: Optional[str] = None) -> str:
        """Retrieve value from environment variable"""
        value = self.env.get(secret_name)
        if not value:
            raise ValueError(f"Environment variable '{secret_name}' not set")
        return value


class SecretsManager:
    """Unified secrets manager - automatically selects best provider"""

    _instance = None
    _provider: Optional[SecretsProvider] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize(
        cls,
        provider_type: str = "auto",
        **kwargs
    ) -> "SecretsManager":
        """
        Initialize secrets manager with selected provider
        
        Args:
            provider_type: 'aws', 'vault', 'env', or 'auto' (auto-detect)
            **kwargs: Provider-specific configuration
        """
        if provider_type == "auto":
            provider_type = cls._auto_detect_provider()
        
        logger.info(f"🔐 Initializing SecretsManager with provider: {provider_type}")
        
        if provider_type == "aws":
            cls._provider = AWSSecretsManagerProvider(**kwargs)
        elif provider_type == "vault":
            cls._provider = HashiCorpVaultProvider(**kwargs)
        elif provider_type == "env":
            cls._provider = EnvSecretsProvider()
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
        
        return cls()

    @staticmethod
    def _auto_detect_provider() -> str:
        """Auto-detect best available provider"""
        import os
        
        # Check for AWS credentials
        if os.getenv("AWS_REGION") or os.getenv("AWS_ACCESS_KEY_ID"):
            logger.info("🔍 Auto-detected AWS Secrets Manager")
            return "aws"
        
        # Check for Vault
        if os.getenv("VAULT_ADDR"):
            logger.info("🔍 Auto-detected HashiCorp Vault")
            return "vault"
        
        # Fallback to environment variables
        logger.info("🔍 Auto-detected Environment Variables (development mode)")
        return "env"

    @classmethod
    def get_secret(cls, secret_name: str) -> Dict[str, Any]:
        """Get entire secret"""
        if not cls._provider:
            raise RuntimeError("SecretsManager not initialized. Call initialize() first.")
        return cls._provider.get_secret(secret_name)

    @classmethod
    def get_secret_value(
        cls, secret_name: str, key: Optional[str] = None
    ) -> str:
        """Get specific secret value"""
        if not cls._provider:
            raise RuntimeError("SecretsManager not initialized. Call initialize() first.")
        return cls._provider.get_secret_value(secret_name, key)

    @classmethod
    def get_provider_type(cls) -> str:
        """Get current provider type"""
        if not cls._provider:
            return "uninitialized"
        return cls._provider.__class__.__name__
