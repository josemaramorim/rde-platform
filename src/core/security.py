from cryptography.fernet import Fernet
from src.core.config import settings


class EncryptionService:
    def __init__(self, key: str = None):
        # Use provided key or settings key
        raw_key = key or settings.ENCRYPTION_KEY
        
        # Ensure key is correctly padded/valid for Fernet (32 bytes base64)
        # This is a simplified fallback for local development if the key isn't a valid Fernet key
        try:
            self.key = raw_key.encode()
            self.cipher_suite = Fernet(self.key)
        except Exception:
            # If the user-provided string isn't a valid 32-byte base64 key, 
            # we need a deterministic fallback for local dev or we error out
            # Here we wrap it (not ideal for production, but ensures it starts)
            import hashlib
            import base64
            hasher = hashlib.sha256()
            hasher.update(raw_key.encode())
            derived_key = base64.urlsafe_b64encode(hasher.digest())
            self.key = derived_key
            self.cipher_suite = Fernet(self.key)

    def encrypt(self, plain_text: str|None) -> str:
        if not plain_text:
            return ""
        return self.cipher_suite.encrypt(plain_text.encode()).decode()

    def decrypt(self, cipher_text: str|None) -> str:
        if not cipher_text:
            return ""
        try:
            return self.cipher_suite.decrypt(cipher_text.encode()).decode()
        except Exception:
            return "ERROR_DECRYPT"


encryption_service = EncryptionService()
