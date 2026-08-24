"""
Gerenciamento de Capital - Planilha RDE
3 sessoes por dia, cada uma com meta de 1% do capital base do dia.
Dentro de cada sessao, usa martingale de recuperacao (2.2x) apos loss.
Apos win, reseta para stake base (1% do saldo atual).
Meta diaria: 3% do capital base do dia.
Capital cresce 3% ao dia (juros compostos) apos bater a meta.
"""


class Management3Pct:
    SESSIONS_PER_DAY = 3
    ENTRIES_PER_SESSION = 3
    SESSION_TARGET_PCT = 0.01   # 1% do capital base por sessao
    DAILY_TARGET_PCT = 0.03     # 3% do capital base por dia
    BASE_STAKE_PCT = 0.01       # stake base = 1% do saldo atual
    RECOVERY_MULTIPLIER = 2.2   # multiplicador de recuperacao apos loss

    def get_base_stake(self, balance: float) -> float:
        """Stake base = 1% do saldo atual."""
        return round(balance * self.BASE_STAKE_PCT, 2)

    def get_session_target(self, balance: float) -> float:
        """Meta da sessao = 1% do capital base do dia."""
        return round(balance * self.SESSION_TARGET_PCT, 2)

    def get_daily_target(self, balance: float) -> float:
        """Meta diaria = 3% do capital base do dia."""
        return round(balance * self.DAILY_TARGET_PCT, 2)


class SessionManager:
    """
    Gerencia 3 sessoes por dia com martingale de recuperacao.

    Fluxo dentro de cada sessao:
      - Entrada 1: stake base (1% do saldo)
      - Se LOSS: entrada 2 = stake_base * 2.2
      - Se LOSS: entrada 3 = stake_base * 2.2^2
      - Se WIN: reseta para stake_base
      - Sessao termina quando: meta atingida OU 3 entradas usadas

    Fluxo entre sessoes:
      - Sessao termina -> avanca para proxima
      - 3 sessoes concluidas -> dia finalizado
    """

    def __init__(self, balance: float):
        self.initial_balance = balance
        self.current_balance = balance
        self.daily_profit = 0.0
        self.current_session = 1
        self.session_entries_used = 0
        self.session_profit = 0.0
        self.session_losses = 0    # losses consecutivos na sessao atual
        self.finished = False
        self.total_trades = 0
        self.total_wins = 0

        self.mgmt = Management3Pct()

    @property
    def stake(self) -> float:
        """Stake da proxima entrada com recuperacao martingale."""
        base = self.mgmt.get_base_stake(self.current_balance)
        if self.session_losses == 0:
            return base
        # Apos loss: stake * 2.2^(losses_consecutivos)
        return round(base * (self.mgmt.RECOVERY_MULTIPLIER ** self.session_losses), 2)

    @property
    def session_target(self) -> float:
        return self.mgmt.get_session_target(self.initial_balance)

    @property
    def daily_target(self) -> float:
        return self.mgmt.get_daily_target(self.initial_balance)

    def can_trade(self) -> bool:
        if self.finished:
            return False
        if self.daily_profit >= self.daily_target:
            return False
        if self.session_entries_used >= Management3Pct.ENTRIES_PER_SESSION:
            return False
        return True

    def new_day(self, new_balance: float = None):
        if new_balance is not None:
            self.initial_balance = new_balance
            self.current_balance = new_balance
        self.daily_profit = 0.0
        self.current_session = 1
        self.session_entries_used = 0
        self.session_profit = 0.0
        self.session_losses = 0
        self.finished = False
        self.total_trades = 0
        self.total_wins = 0

    def update_balance(self, new_balance: float):
        self.current_balance = new_balance

    def register_result(self, profit: float) -> dict:
        self.session_entries_used += 1
        self.session_profit += profit
        self.daily_profit += profit
        self.total_trades += 1

        is_win = profit > 0

        actual_stake = round(
            self.mgmt.get_base_stake(self.current_balance)
            * (self.mgmt.RECOVERY_MULTIPLIER ** self.session_losses),
            2
        )

        if is_win:
            self.session_losses = 0
            self.total_wins += 1
        else:
            self.session_losses += 1

        result = {
            "session": self.current_session,
            "entry": self.session_entries_used,
            "session_profit": round(self.session_profit, 2),
            "daily_profit": round(self.daily_profit, 2),
            "daily_target": self.daily_target,
            "session_target": self.session_target,
            "stake_used": round(actual_stake, 2),
            "next_stake": round(self.stake, 2),
            "session_losses": self.session_losses,
            "session_completed": False,
            "all_done": False,
            "daily_goal_hit": False,
        }

        daily_was_hit = self.daily_profit >= self.daily_target
        session_was_hit = self.session_profit >= self.session_target
        entries_exhausted = self.session_entries_used >= Management3Pct.ENTRIES_PER_SESSION

        if session_was_hit:
            result["session_completed"] = True
            self._advance_session()

        if daily_was_hit:
            result["daily_goal_hit"] = True
            result["session_completed"] = True
            self.finished = True

        if entries_exhausted and not session_was_hit and not daily_was_hit:
            result["session_completed"] = True
            self._advance_session()

        result["all_done"] = self.finished
        result["next_session"] = self.current_session
        return result

    def _advance_session(self):
        self.current_session += 1
        self.session_entries_used = 0
        self.session_profit = 0.0
        # NAO reseta session_losses aqui!
        # O martingale continua entre sessoes ate ganhar.
        if self.current_session > Management3Pct.SESSIONS_PER_DAY:
            self.finished = True

    def get_status(self) -> dict:
        win_rate = round((self.total_wins / self.total_trades * 100), 1) if self.total_trades > 0 else 0.0
        return {
            "initial_balance": round(self.initial_balance, 2),
            "current_balance": round(self.current_balance, 2),
            "daily_profit": round(self.daily_profit, 2),
            "daily_target": self.daily_target,
            "daily_progress_pct": round(
                (self.daily_profit / self.daily_target * 100), 1
            ) if self.daily_target > 0 else 0,
            "current_session": self.current_session,
            "session_entries_used": self.session_entries_used,
            "session_profit": round(self.session_profit, 2),
            "session_target": self.session_target,
            "session_losses": self.session_losses,
            "stake": round(self.stake, 2),
            "base_stake": round(self.mgmt.get_base_stake(self.current_balance), 2),
            "finished": self.finished,
            "total_trades": self.total_trades,
            "wins": self.total_wins,
            "losses": self.total_trades - self.total_wins,
            "win_rate": win_rate,
            "gale_level": self.session_losses,
        }


ai_management = Management3Pct()


