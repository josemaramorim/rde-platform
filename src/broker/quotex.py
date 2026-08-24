"""
Quotex broker adapter for RDE Platform.

Uses the quotexpy package (pip install quotexpy).
Authentication is via email + password.

References:
  - https://pypi.org/project/quotexpy/
  - https://github.com/zagmi/qxbroker (source)
"""
import asyncio
import logging
import re
import shutil
from src.broker.base import BaseBroker
from src.broker._utils import run_async

try:
    from quotexpy import Quotex as QuotexClient
except ImportError:
    QuotexClient = None

logger = logging.getLogger("rde")


def _detect_chrome_major_version() -> int | None:
    """Retorna a versao principal (major) do Google Chrome instalado.

    O undetected-chromedriver baixa um ChromeDriver que deve bater com a
    versao do Chrome. Se nao bater, da erro
    ('This version of ChromeDriver only supports Chrome version X').
    Detectar a versao e passar version_main alinha os dois.
    """
    import os
    import subprocess

    exe = shutil.which("chrome") or shutil.which("google-chrome")
    if not exe:
        for path in (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ):
            if os.path.exists(path):
                exe = path
                break
    if not exe:
        return None
    # `chrome --version` trava quando ja ha uma instancia aberta, entao
    # lemos a versao direto das propriedades do arquivo via PowerShell.
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item -LiteralPath '{exe}').VersionInfo.ProductVersion"],
            capture_output=True, text=True, timeout=15,
        )
        m = re.search(r"(\d+)\.\d+\.\d+", ps.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        return None
    return None


def _detect_chrome_path() -> str | None:
    """Retorna o caminho do executavel do Chrome instalado (Windows/Linux).

    O undetected-chromedriver nao acha o Chrome sozinho no Windows
    (procura por 'chrome'/'google-chrome' no PATH). Apontar o binario
    manualmente evita o erro 'Chrome is not installed, did you forget?'.
    """
    import os
    exe = shutil.which("chrome") or shutil.which("google-chrome")
    if exe:
        return exe
    for path in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ):
        if os.path.exists(path):
            return path
    return None


def _patch_quotex_chromedriver():
    """Forca o undetected-chromedriver (usado pelo quotexpy) a usar o
    ChromeDriver compativel com a versao do Chrome instalada e a achar
    o binario do Chrome no Windows.

    Nao trocamos uc.Chrome (o __init__ do undetected usa super(Chrome, self)
    e quebraria). Em vez disso:
      - adicionamos o dir do Chrome ao PATH (Windows nao acha sozinho);
      - patchamos o Patcher para injetar version_main, assim o driver
        baixado casa com a versao do Chrome instalada.
    """
    try:
        import os
        import undetected_chromedriver as uc
        major = _detect_chrome_major_version()
        chrome_path = _detect_chrome_path()
        if not major and not chrome_path:
            return
        # Garante que o undetected ache o binario do Chrome no Windows
        if chrome_path:
            d = os.path.dirname(chrome_path)
            if d and d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

        if major:
            _OrigPatcherInit = uc.patcher.Patcher.__init__

            def _patched_patcher_init(self, *a, **k):
                if k.get("version_main") is None:
                    k["version_main"] = major
                return _OrigPatcherInit(self, *a, **k)

            uc.patcher.Patcher.__init__ = _patched_patcher_init

        logger.info(
            f"Quotex: ChromeDriver alinhado (v{major}, exe={chrome_path})"
        )
    except Exception as e:
        logger.warning(f"Quotex: nao foi possivel alinhar ChromeDriver: {e}")


class QuotexBroker(BaseBroker):
    def __init__(self, email: str, password: str, is_demo: bool = True):
        if QuotexClient is None:
            raise RuntimeError(
                "quotexpy is not installed.\n"
                "Install with: pip install quotexpy"
            )
        self.email = email
        self.password = password
        self.is_demo = is_demo
        self.client: QuotexClient | None = None
        self.trade_id: str | None = None

    def connect(self):
        run_async(self.async_connect())

    def send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        return run_async(self.async_send_order(symbol, stake, direction, duration))

    def get_balance(self) -> float:
        return run_async(self.async_get_balance())

    def get_contract_status(self, order_id: str) -> str:
        return run_async(self.async_get_contract_status(order_id))

    def disconnect(self):
        if self.client:
            try:
                run_async(self.client.close())
            except Exception:
                pass
            self.client = None

    def _ensure_connected(self) -> bool:
        """Verifica se a conexao esta viva. Reconecta se necessario."""
        try:
            if self.client is None:
                self.connect()
                return True
            return True
        except Exception as e:
            logger.warning(f"Conexao Quotex perdida ({e}). Reconectando...")
            try:
                self.connect()
                return True
            except Exception as e2:
                logger.error(f"Falha ao reconectar Quotex: {e2}")
                return False

    async def _ensure_connected_async(self) -> bool:
        """Versao async do ensure_connected."""
        try:
            if self.client is None:
                await self.async_connect()
                return True
            bal = await self.client.get_balance()
            if bal is None:
                raise ConnectionError("Balance check returned None")
            return True
        except Exception as e:
            logger.warning(f"Conexao Quotex perdida ({e}). Reconectando...")
            try:
                await self.async_connect()
                return True
            except Exception as e2:
                logger.error(f"Falha ao reconectar Quotex: {e2}")
                return False

    async def async_connect(self):
        _patch_quotex_chromedriver()
        self.client = QuotexClient(email=self.email, password=self.password)
        connected = await self.client.connect()
        if not connected:
            raise ConnectionError(
                "Quotex: Connection failed. Check credentials."
            )
        mode = "PRACTICE" if self.is_demo else "REAL"
        self.client.change_account(mode)
        logger.info(f"Quotex connected ({'Demo' if self.is_demo else 'Real'})")

    async def async_send_order(
        self, symbol: str, stake: float, direction: str, duration: int = 1
    ) -> dict:
        if not await self._ensure_connected_async():
            return {"status": "error", "result": "Falha ao reconectar Quotex"}

        try:
            action = "call" if direction.upper() == "CALL" else "put"
            status, result = await self.client.trade(
                action=action,
                amount=stake,
                asset=symbol,
                duration=duration,
            )
            trade_id = self.client.api.trade_id if self.client else None
            logger.info(
                f"Quotex order: {trade_id} | "
                f"{direction} {symbol} ${stake} | status={status}"
            )
            return {
                "status": "ok" if status else "error",
                "result": str(result),
                "contract_id": trade_id,
            }
        except Exception as e:
            logger.error(f"Quotex order error for {symbol}: {e}")
            return {"status": "error", "result": str(e)}

    async def async_get_contract_status(self, order_id: str) -> str:
        try:
            won = await self.client.check_win(order_id, revisions=10)
            return "won" if won else "lost"
        except Exception as e:
            logger.error(f"Quotex status check error: {e}")
            return "error"

    async def async_get_balance(self):
        try:
            return await self.client.get_balance()
        except Exception as e:
            logger.error(f"Quotex balance error: {e}")
            return 0.0
