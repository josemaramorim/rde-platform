"""
Broker factory -- resolves the correct broker adapter for a given user.

Reads credentials from the `broker_settings` table (preferred) or
falls back to the legacy fields on the User model.

Supported brokers:
  - iqoption     -> IQOptionBroker (email + password)
  - deriv        -> DerivBroker (api_token)
"""
import logging
from src.broker.iqoption import IQOptionBroker
from src.broker.deriv import DerivBroker

logger = logging.getLogger("rde")


def get_broker(user, db=None):
    broker_name = (user.broker or "").lower()

    setting = None
    if hasattr(user, 'broker_settings') and user.broker_settings:
        setting = next(
            (bs for bs in user.broker_settings
             if getattr(bs, 'broker_name', '').lower() == broker_name and bs.is_active),
            None,
        )

    def _decrypt(cipher_text):
        if not cipher_text:
            return None
        try:
            from src.core.security import encryption_service
            decrypted = encryption_service.decrypt(cipher_text)
            return decrypted if decrypted != "ERROR_DECRYPT" else cipher_text
        except Exception:
            return cipher_text

    if setting and hasattr(setting, 'is_demo'):
        is_demo = bool(setting.is_demo)
    else:
        is_demo = not (hasattr(user, 'plan') and user.plan and not user.plan.is_demo)

    if broker_name == "iqoption":
        email = None
        password = None
        if setting and setting.api_token:
            token = _decrypt(setting.api_token)
            if token and "|||" in token:
                email, password = token.split("|||", 1)
            elif setting.iq_email:
                email = setting.iq_email
                password = token
        if not email:
            email = user.iq_email
        if not password and user.iq_password:
            password = _decrypt(user.iq_password)
        if not email or not password:
            raise ValueError("IQ Option credentials are not configured for this user.")
        broker = IQOptionBroker(email=email, password=password, is_demo=is_demo)
        broker.connect()
        return broker

    elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
        token = None
        if setting and setting.api_token:
            token = _decrypt(setting.api_token)
        if not token and hasattr(user, "api_token"):
            token = _decrypt(user.api_token)
        if not token:
            raise ValueError("Deriv API token is not configured for this user.")
        app_id = getattr(setting, "deriv_app_id", None) if setting else None
        broker = DerivBroker(api_token=token, is_demo=is_demo, app_id=app_id or "16929")
        broker.connect()
        return broker

    else:
        raise ValueError(f"Unsupported broker: '{broker_name}'")
