"""
Telegram Integration for RDE Platform
Sends trading signals and notifications to Telegram Bot
"""

import logging
import asyncio
from typing import Optional, Dict, Any
import aiohttp
from src.core.config import settings

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram Bot for sending trading signals"""
    
    # Load from settings (centralized in .env)
    TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = settings.TELEGRAM_CHAT_ID
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    @classmethod
    async def send_signal(
        cls,
        signal_type: str,
        pair: str,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
        confidence: float,
        user_name: str = "Sistema"
    ) -> bool:
        """
        Send trading signal to Telegram
        
        Args:
            signal_type: "BUY" or "SELL"
            pair: Trading pair (e.g., "EURUSD")
            entry_price: Entry price
            take_profit: Take profit price
            stop_loss: Stop loss price
            confidence: Confidence level (0-100%)
            user_name: User who generated signal
        """
        try:
            message = cls._format_signal_message(
                signal_type=signal_type,
                pair=pair,
                entry_price=entry_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                confidence=confidence,
                user_name=user_name
            )
            
            await cls.send_message(message)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send signal to Telegram: {e}")
            return False
    
    @classmethod
    async def send_message(cls, text: str, parse_mode: str = "HTML") -> bool:
        """Send text message to Telegram"""
        try:
            url = f"{cls.TELEGRAM_API_URL}/sendMessage"
            payload = {
                "chat_id": cls.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"✅ Telegram message sent")
                        return True
                    else:
                        logger.error(f"❌ Telegram API error: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Error sending Telegram message: {e}")
            return False
    
    @classmethod
    async def send_signal_image(
        cls,
        image_path: str,
        caption: str = ""
    ) -> bool:
        """Send signal with chart image"""
        try:
            url = f"{cls.TELEGRAM_API_URL}/sendPhoto"
            
            with open(image_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': cls.TELEGRAM_CHAT_ID,
                    'caption': caption,
                    'parse_mode': 'HTML'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, files=files, data=data) as response:
                        if response.status == 200:
                            logger.info(f"✅ Telegram image sent")
                            return True
                        else:
                            logger.error(f"❌ Telegram API error: {response.status}")
                            return False
        except Exception as e:
            logger.error(f"❌ Error sending Telegram image: {e}")
            return False
    
    @classmethod
    def _format_signal_message(
        cls,
        signal_type: str,
        pair: str,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
        confidence: float,
        user_name: str
    ) -> str:
        """Format trading signal message"""
        
        signal_emoji = "🟢 BUY" if signal_type == "BUY" else "🔴 SELL"
        confidence_bar = "█" * int(confidence / 10) + "░" * (10 - int(confidence / 10))
        
        message = f"""
<b>📊 SINAL DE TRADING</b>

<b>{signal_emoji}</b> {pair}

<b>Entrada:</b> {entry_price}
<b>Take Profit:</b> {take_profit}
<b>Stop Loss:</b> {stop_loss}

<b>Confiança:</b>
{confidence_bar} {confidence:.1f}%

<b>Usuário:</b> {user_name}
<b>Plataforma:</b> RDE

---
💡 Analise sempre antes de operar
⚠️ Risco moderado
"""
        return message.strip()
    
    @classmethod
    async def send_user_notification(
        cls,
        user_name: str,
        notification_type: str,
        message: str
    ) -> bool:
        """Send notification to user"""
        
        icons = {
            "login": "🔐",
            "logout": "🚪",
            "signal": "📊",
            "payment": "💳",
            "error": "❌",
            "success": "✅",
            "warning": "⚠️"
        }
        
        icon = icons.get(notification_type, "ℹ️")
        
        formatted_message = f"""
{icon} <b>{notification_type.upper()}</b>

<b>Usuário:</b> {user_name}
<b>Mensagem:</b> {message}

<i>RDE Platform</i>
"""
        return await cls.send_message(formatted_message.strip())
    
    @classmethod
    async def test_connection(cls) -> bool:
        """Test Telegram connection"""
        try:
            url = f"{cls.TELEGRAM_API_URL}/getMe"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        bot_name = data.get('result', {}).get('username', 'Unknown')
                        logger.info(f"✅ Telegram Bot connected: @{bot_name}")
                        return True
                    else:
                        logger.error(f"❌ Telegram connection failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Telegram connection error: {e}")
            return False


# Signal emission helper
async def emit_buy_signal(
    pair: str,
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    confidence: float,
    user_name: str = "Sistema"
):
    """Emit BUY signal to Telegram"""
    return await TelegramBot.send_signal(
        signal_type="BUY",
        pair=pair,
        entry_price=entry_price,
        take_profit=take_profit,
        stop_loss=stop_loss,
        confidence=confidence,
        user_name=user_name
    )


async def emit_sell_signal(
    pair: str,
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    confidence: float,
    user_name: str = "Sistema"
):
    """Emit SELL signal to Telegram"""
    return await TelegramBot.send_signal(
        signal_type="SELL",
        pair=pair,
        entry_price=entry_price,
        take_profit=take_profit,
        stop_loss=stop_loss,
        confidence=confidence,
        user_name=user_name
    )
