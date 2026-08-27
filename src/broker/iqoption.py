"""
IQ Option broker adapter for RDE Platform.
Supports dynamic Demo/Real account switching via is_demo parameter.
"""
import re
import logging
import time
import threading
import random
from src.broker.base import BaseBroker

try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError as e:
    IQ_Option = None
    _IMPORT_ERROR = str(e)

logger = logging.getLogger("rde")

_RECONNECT_LOCK = threading.Lock()


class IQOptionBroker(BaseBroker):

    def __init__(self, email: str, password: str, is_demo: bool = True):
        self.email = email
        self.password = password
        self.is_demo = is_demo
        self.api = None
        self._last_connect_time = 0.0
        self._asset_map = {}
        self._asset_base_index = {}
        self._open_map = {}  # nome_completo -> bool (aberto agora na corretora)
        self._preferred_asset = None
        self._unavailable_assets = set()
        self._max_unavailable_attempts = 2
        
    def _validate_credentials(self) -> bool:
        """Valida se as credenciais do ativo são válidas antes de tentar conectar."""
        if not self.email or not self.password:
            logger.warning(f"Credentials inválidas: email ou password não fornecidos")
            return False

        if not isinstance(self.email, str) or not isinstance(self.password, str):
            logger.warning(f"Credentials inválidas: email ou password não são strings válidas")
            return False

        if len(self.email) < 3 or len(self.password) < 3:  # Comprimento mínimo básico
            logger.warning(f"Credentials inválidas: email ou password muito curtos")
            return False

        logger.info(f"Credentials validadas para broker: {self.email}")
        return True

    @staticmethod
    def _is_otc(symbol: str) -> bool:
        """Detecta se o ativo e OTC (market sintético da corretora)."""
        s = symbol.upper()
        return "-OTC" in s or "_OTC" in s or "OTC" in s

    def is_market_open(self) -> bool:
        """Verifica se o mercado forex está aberto (UTC-3).
        Fecha às 16:00 (sex: 14:00), reabre à 00:00. Fim de semana fechado."""
        try:
            import datetime
            # UTC-3 = UTC - 3h
            now_utc = datetime.datetime.utcnow()
            now_local = now_utc - datetime.timedelta(hours=3)
            weekday = now_local.weekday()  # 0=seg, 6=dom
            hour = now_local.hour

            # Fim de semana: sábado(5) e domingo(6) fechado
            if weekday >= 5:
                return False
            # Sexta: fecha às 14:00
            if weekday == 4 and hour >= 14:
                return False
            # Fecha às 16:00 (e reabre à 00:00)
            if hour >= 16:
                return False
            return True
        except Exception:
            return True  # Em caso de dúvida, tenta operar

    def is_asset_open(self, symbol: str) -> bool:
        """Verifica se a variacao EXATA do ativo está aberta na corretora agora.

        Nao troca spot por OTC: 'GBPUSD' e 'GBPUSD-OTC' sao verificados
        independentemente. Se nao temos o mapa, recarrega.
        """
        if not self._asset_map:
            self._wait_init()
        if not self._open_map:
            self._refresh_open_status()
        norm = symbol.upper().replace("_", "-")
        for key in self._asset_map:
            if key.upper().replace("_", "-") == norm:
                return self._variation_open(key)
        return False

    def _fully_disconnect(self):
        """Fecha todas as camadas de conexao e limpa referencias."""
        if self.api is None:
            return
        try:
            if hasattr(self.api, 'api') and self.api.api:
                try:
                    self.api.api.close()
                except Exception:
                    pass
                self.api.api = None
            if hasattr(self.api, 'socket') and self.api.socket:
                try:
                    self.api.socket.close()
                except Exception:
                    pass
                self.api.socket = None
        except Exception:
            pass
        self.api = None

    def _build_asset_map(self):
        """Extrai lista de ativos disponiveis do init result e cria mapping."""
        self._asset_map = {}
        self._asset_base_index = {}
        self._preferred_asset = None
        raw_res = getattr(self.api.api, 'api_option_init_all_result', None)
        result = raw_res[0] if isinstance(raw_res, list) and len(raw_res) > 0 else raw_res
        if not isinstance(result, dict) or not result.get("isSuccessful"):
            logger.warning("init result nao disponivel para asset map")
            return
        for cat in ("turbo", "binary"):
            actives = result.get("result", {}).get(cat, {}).get("actives", {})
            for aid, adata in actives.items():
                raw = adata.get("name", "")
                name = raw[raw.index(".") + 1:] if "." in raw else raw
                commission = adata.get("option", {}).get("profit", {}).get("commission", 0)
                entry = (name, int(aid), int(commission))
                # Chave exata (nome completo)
                self._asset_map.setdefault(name, []).append(entry)
                # Indice por base (apenas p/ fallback)
                base_symbol = name.split("-")[0].split("_")[0]
                self._asset_base_index.setdefault(base_symbol, []).append(entry)
        # Log ativos encontrados
        for sym, entries in list(self._asset_map.items())[:10]:
            logger.info(f"  {sym}: {entries}")
        logger.info(f"Asset map construido com {len(self._asset_map)} ativos e {len(self._asset_base_index)} base symbols")

    def _wait_init(self, timeout: int = 5):
        """Aguarda get_all_init completar e constroi asset map."""
        if self.api is None or not hasattr(self.api, 'api'):
            return
        try:
            def _check_ok(res):
                if isinstance(res, dict): return bool(res.get("isSuccessful"))
                if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict): return bool(res[0].get("isSuccessful"))
                return False

            # Se o resultado ja existe (veio na conexao), constroi direto!
            res = getattr(self.api.api, 'api_option_init_all_result', None)
            if _check_ok(res):
                self._build_asset_map()
                self._refresh_open_status()
                return

            logger.info(f"Aguardando api_option_init_all (timeout={timeout}s)...")
            self.api.api.get_api_option_init_all()
            deadline = time.time() + timeout
            while time.time() < deadline:
                result = getattr(self.api.api, 'api_option_init_all_result', None)
                if _check_ok(result):
                    logger.info("api_option_init_all concluido com sucesso.")
                    self._build_asset_map()
                    self._refresh_open_status()
                    return
                time.sleep(0.3)
            logger.warning(f"api_option_init_all timeout ({timeout}s). Continuando...")
        except Exception as e:
            logger.warning(f"get_all_init falhou (continuando): {e}")

    def _refresh_open_status(self):
        """Consulta a corretora e monta self._open_map[nome_completo] = aberto_agora.

        Usa get_all_open_time() que reflete o horario de operacao REAL de cada
        ativo (enabled / is_suspended por ativo). OTC opera 24/7; spot forex
        segue o horario de mercado. Assim a plataforma so opera a variacao
        efetivamente aberta e nunca troca spot por OTC (nem vice-versa).
        """
        self._open_map = {}
        if self.api is None:
            return
        try:
            open_time = self.api.api.get_all_open_time()
            if not open_time:
                return
            for category in ("turbo", "binary", "other"):
                cat_data = open_time.get(category, {}) if isinstance(open_time, dict) else {}
                for name, info in cat_data.items():
                    if isinstance(info, dict) and "open" in info:
                        self._open_map[name] = bool(info["open"])
            logger.info(f"Open-status atualizado: {sum(1 for v in self._open_map.values() if v)} ativos abertos de {len(self._open_map)}")
        except Exception as e:
            logger.warning(f"Falha ao consultar open-status: {e}")

    def _variation_open(self, name: str) -> bool:
        """Verifica se uma variacao especifica (nome completo) esta aberta agora."""
        # Tenta match exato primeiro
        if name in self._open_map:
            return self._open_map[name]
        # Normaliza -/_ e case
        norm = name.upper().replace("_", "-")
        for key, val in self._open_map.items():
            if key.upper().replace("_", "-") == norm:
                return val
        # Se nao temos dados de open, recarrega e tenta de novo
        if not self._open_map:
            self._refresh_open_status()
            if name in self._open_map:
                return self._open_map[name]
            for key, val in self._open_map.items():
                if key.upper().replace("_", "-") == norm:
                    return val
        # So depois de tentar recarregar, assume aberto como fallback
        logger.warning(f"Variacao '{name}' sem dados de open-status. Assumindo aberto como fallback.")
        return True

    def connect(self, wait_init: bool = True):
        if IQ_Option is None:
            raise RuntimeError(f"iqoptionapi is not installed: {_IMPORT_ERROR}")

        with _RECONNECT_LOCK:
            self._fully_disconnect()
            time.sleep(0.5)

            self.api = IQ_Option(self.email, self.password)
            check, reason = self.api.connect()
            if not check:
                self.api = None
                raise ConnectionError(f"IQ Option connection failed: {reason}")

            account_type = "PRACTICE" if self.is_demo else "REAL"
            self.api.change_balance(account_type)
            self._last_connect_time = time.time()
            logger.info(f"IQ Option connected ({account_type})")

            # Carrega o asset map apenas se explicitamente solicitado (ex: ao processar operacoes)
            if wait_init:
                self._wait_init(timeout=5)

    def _is_alive(self) -> bool:
        """Verifica se a conexao esta viva tentando obter saldo."""
        if self.api is None:
            return False
        try:
            bal = self.api.get_balance()
            if bal is None or bal < 0:
                return False
            return True
        except Exception:
            return False

    def _ensure_connected(self) -> bool:
        """Verifica se a conexao esta viva e asset map populado. Reconecta se necessario."""
        if self._is_alive():
            if not self._asset_map:
                logger.info("Conexao viva. Populando asset map sem desconectar...")
                self._wait_init(timeout=5)
            return True

        logger.warning("Conexao IQ Option perdida. Reconectando...")
        self._fully_disconnect()

        for attempt in range(3):
            try:
                time.sleep(1 + attempt)
                self.connect(wait_init=True)
                if self._is_alive():
                    return True
                logger.warning(f"Reconexao {attempt+1}/3: conexao criada mas saldo invalido.")
                self._fully_disconnect()
            except Exception as e:
                logger.warning(f"Reconexao {attempt+1}/3 falhou: {e}")
                self._fully_disconnect()

        logger.error("Falha ao reconectar IQ Option apos 3 tentativas.")
        return False

    def _resolve_asset(self, symbol: str):
        """Retorna (real_name, asset_id, commission) do ativo solicitado.

        REGRA: opera EXATAMENTE o símbolo do sinal (ex: "GBPUSD-OTC").
        Nunca troca por outro ativo (ex: GBPUSD base) nem por variação diferente.
        Busca:
          1. match exato do nome completo (GBPUSD-OTC)
          2. variações normais do MESMO símbolo (GBPUSD-OTC, GBPUSD_otc, gbpusd-otc)
          3. fallback por base_symbol APENAS se o nome exato não existir,
             e ainda assim devolve as entradas daquele base (não de outro ativo)
        """
        # 1. Match exato
        if symbol in self._asset_map and self._asset_map[symbol]:
            entries = self._asset_map[symbol]
            entries.sort(key=lambda e: e[2])
            return entries[0]

        # 2. Variações do mesmo símbolo (normaliza -/_ e case)
        norm_target = symbol.upper().replace("_", "-")
        for key, entries in self._asset_map.items():
            if key.upper().replace("_", "-") == norm_target and entries:
                sorted_entries = sorted(entries, key=lambda e: e[2])
                return sorted_entries[0]

        # 3. Fallback por base_symbol (só se o nome exato não existir na corretora)
        base = norm_target.split("-")[0].split("_")[0]
        base_entries = self._asset_base_index.get(base, [])
        if base_entries:
            logger.warning(f"Ativo exato '{symbol}' nao encontrado; usando base '{base}' como fallback.")
            sorted_entries = sorted(base_entries, key=lambda e: e[2])
            return sorted_entries[0]

        logger.warning(f"Ativo '{symbol}' nao encontrado na corretora. Keys: {list(self._asset_map.keys())[:10]}")
        return None, None, 0

    def _buyv3(self, asset_id: int, stake: float, direction: str, duration: int) -> tuple:
        """Chama buyv3 diretamente com o ID correto do ativo."""
        api = self.api.api
        api.buy_multi_option = {}
        api.result = None
        req_id = str(random.randint(0, 10000))
        try:
            api.buyv3(float(stake), asset_id, direction, int(duration), req_id)
        except Exception as e:
            return False, str(e)
        # Aguarda resposta com timeout ajustado
        for _ in range(20):
            multi = api.buy_multi_option.get(req_id, {})
            if "message" in multi:
                return False, multi["message"]
            if multi.get("id"):
                return True, multi["id"]
            if api.result is not None:
                order_id = multi.get("id")
                if order_id:
                    return True, order_id
                # Fallback: usa o result se for um ID numérico válido
                if isinstance(api.result, (int, str)) and str(api.result).isdigit():
                    return True, str(api.result)
                return False, "ordem sem ID valido"
            time.sleep(0.5)
        return False, "timeout"

    def _get_payouts(self, symbol: str) -> dict:
        """Retorna dict com payout de cada tipo usando commission do init result."""
        payouts = {"turbo": 0, "binary": 0, "digital": 0}
        entries = self._asset_map.get(symbol, [])
        for name, aid, commission in entries:
            cat = "binary" if "binary" in name.lower() else "turbo"
            if payouts.get(cat, 0) < (100 - commission):
                payouts[cat] = 100 - commission
        return payouts

    def send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        if not self._ensure_connected():
            return {"status": "error", "result": "Falha ao reconectar IQ Option"}

        symbol = symbol.upper()
        dir_clean = direction.lower()
        is_otc = self._is_otc(symbol)

        # Bloqueio de mercado: so para pares spot puros (nao OTC)
        if not is_otc and not self.is_market_open():
            logger.error("MERCADO FECHADO (horario forex UTC-3). Nenhuma ordem spot sera aberta.")
            return {"status": "error", "result": "Mercado fechado agora"}

        # Recarrega asset map / open-status para refletir estado atual da corretora
        if not self._asset_map:
            logger.warning("Asset map vazio! Recarregando...")
            self._wait_init()
        if not self._open_map:
            self._refresh_open_status()

        # --- PASSO 1: Busca candidates por match exato + normalizacoes ---
        norm = symbol.upper().replace("_", "-")
        candidates = self._asset_map.get(symbol, []) or self._asset_map.get(norm, [])
        if not candidates:
            for key, vals in self._asset_map.items():
                if key.upper().replace("_", "-") == norm and vals:
                    candidates = vals
                    break

        # --- PASSO 2: Se nao achou, usa _resolve_asset (fallback por base_symbol) ---
        if not candidates:
            resolved = self._resolve_asset(symbol)
            if resolved and resolved[0]:
                real_name, aid, commission = resolved
                candidates = [(real_name, aid, commission)]
                logger.info(f"[RESOLVE] Ativo '{symbol}' resolvido via fallback -> '{real_name}' (id={aid})")

        # --- PASSO 3: Se ainda nada, tenta variants com OTC/spot complementar ---
        if not candidates:
            otc_variant = symbol + "-OTC" if not is_otc else re.sub(r'[-_]OTC[A-Z]?$', '', symbol)
            candidates = self._asset_map.get(otc_variant, [])
            if not candidates:
                for key, vals in self._asset_map.items():
                    if key.upper().replace("_", "-") == otc_variant.upper().replace("_", "-") and vals:
                        candidates = vals
                        break
            if candidates:
                logger.info(f"[FALLBACK] Ativo '{symbol}' nao encontrado; usando variante '{otc_variant}'")

        if not candidates:
            logger.error(f"Ativo '{symbol}' NAO existe na corretora. "
                         f"Keys disponiveis: {list(self._asset_map.keys())[:20]}")
            return {"status": "error", "result": f"Ativo {symbol} inexistente na corretora"}

        # --- PASSO 4: Filtra variacoes ABERTAS, mas aceita todas como fallback ---
        entries = [e for e in candidates if self._variation_open(e[0])]
        if not entries:
            # Nenhuma variacao reportada como aberta — usa todas mesmo assim
            # (OTC opera 24/7 e _open_map pode nao refletir isso)
            entries = candidates
            logger.warning(f"Nenhuma variacao de '{symbol}' confirmada aberta. "
                           f"Usando {len(entries)} variacao(oes) disponivel(is).")
        entries = sorted(entries, key=lambda e: e[2])

        last_err = ""
        for name, aid, commission in entries:
            payout = 100 - commission
            logger.info(f"Tentando {symbol} ({name}, id={aid}, payout={payout}%): {dir_clean.upper()} ${stake}")
            for attempt in range(3):
                status, oid = self._buyv3(aid, stake, dir_clean, duration)
                if status:
                    logger.info(f"Ordem executada: {symbol} {dir_clean} id={oid} (variacao {name})")
                    return {"status": "ok", "result": f"Sucesso ({payout}%)", "order_id": oid,
                            "variation": name, "payout": payout}
                err = oid if oid else "sem resposta"
                err_lower = str(err).lower()
                skip_errors = ["not available", "invalid", "not found", "does not exist",
                               "inactive", "suspended", "closed", "unavailable"]
                if any(kw in err_lower for kw in skip_errors):
                    last_err = err
                    logger.warning(f"{name} indisponivel agora: {err}. Tentando proxima variacao...")
                    break
                logger.warning(f"Tentativa {attempt+1}/3 para {name} falhou: {err}")
                last_err = err
                time.sleep(5)

        return {"status": "error", "result": f"Todas as variacoes de {symbol} fecharam/recusaram: {last_err}"}

    async def async_send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        """Versao async: executa send_order num executor para nao bloquear o event loop."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.send_order, symbol, stake, direction, duration)

    def get_balance(self) -> float:
        if not self._is_alive():
            return 0.0
        return self.api.get_balance()

    def get_contract_status(self, order_id: str) -> str:
        """Verifica resultado da ordem no IQ Option de forma precisa."""
        if not order_id or not self._is_alive():
            return "error"

        try:
            order_num = int(order_id)
        except Exception:
            order_num = None

        # 1. Tenta check_win_v3 (Binarias / Turbo)
        if order_num is not None:
            try:
                async_orders = getattr(self.api, "async_orders", {})
                if order_num in async_orders or str(order_num) in async_orders:
                    net_profit = self.api.check_win_v3(order_num)
                    if isinstance(net_profit, (int, float)):
                        return "won" if net_profit > 0 else "lost"
            except Exception as e:
                logger.debug(f"check_win_v3 falhou para {order_id}: {e}")

        # 2. Tenta check_win_digital_v2 (Digitais)
        if order_num is not None:
            try:
                ok, net_profit = self.api.check_win_digital_v2(order_num)
                if ok and isinstance(net_profit, (int, float)):
                    return "won" if net_profit > 0 else "lost"
            except Exception as e:
                logger.debug(f"check_win_digital_v2 falhou para {order_id}: {e}")

        # 3. Consulta closed_options recentes
        try:
            api = self.api.api
            api.get_options_v2_data = None
            api.get_options_v2(50, "binary,turbo")
            deadline = time.time() + 5
            while time.time() < deadline:
                data = getattr(api, 'get_options_v2_data', None)
                if data is not None:
                    break
                time.sleep(0.5)

            if data and isinstance(data, dict) and "msg" in data:
                closed = data.get("msg", {}).get("closed_options", [])
                for opt in closed:
                    raw_ids = opt.get("id", [])
                    matched = False
                    if order_num is not None and isinstance(raw_ids, list):
                        matched = order_num in [int(i) for i in raw_ids if str(i).isdigit()]
                    elif str(raw_ids) == str(order_id):
                        matched = True

                    if matched:
                        win = opt.get("win", "equal")
                        amount = float(opt.get("amount", 0))
                        win_amount = float(opt.get("win_amount", 0))
                        profit = win_amount - amount if win != "equal" else 0
                        return "won" if profit > 0 else "lost"
        except Exception as e:
            logger.debug(f"closed_options check falhou: {e}")

        logger.warning(f"Não foi possível determinar o resultado da ordem IQ Option {order_id}")
        return "error"

    async def async_get_contract_status(self, order_id: str) -> str:
        """Versao async: executa get_contract_status num executor para nao bloquear o event loop."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_contract_status, order_id)

    def disconnect(self):
        self._fully_disconnect()
