from sqlalchemy import select
from src.models.user import SignalUsage, User
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession


# Safe mode caps
SAFE_MAX_PCT = 0.10       # 10% of balance per cycle
SAFE_MAX_MG_LEVELS = 4    # Maximum martingale levels in safe mode


def check_plan_limits(db, user: User):
    """
    Validates daily signal count and stake vs. plan limits.
    Returns (allowed: bool, message: str).
    """
    plan = user.plan
    if not plan:
        return False, "No plan assigned. Contact support."

    # Check daily usage
    usage = (
        db.query(SignalUsage)
        .filter_by(user_id=user.id, date=date.today())
        .first()
    )
    if not usage:
        usage = SignalUsage(user_id=user.id, count=0)
        db.add(usage)
        db.commit()
        db.refresh(usage)

    if usage.count >= plan.max_signals_per_day:
        return False, f"Daily signal limit reached ({plan.max_signals_per_day}/day on {plan.name} plan)."

    if user.stake > plan.max_stake:
        return False, f"Stake ${user.stake} exceeds {plan.name} plan limit of ${plan.max_stake}."

    # Increment usage
    usage.count += 1
    db.commit()
    return True, "OK"


async def async_check_plan_limits(db: AsyncSession, user: User):
    """
    Async version of plan limit check.
    """
    from src.models.user import Plan as PlanModel

    # Fetch plan explicitly to avoid lazy load in async context
    if user.plan_id is None:
        return False, "No plan assigned."

    plan_result = await db.execute(
        select(PlanModel).where(PlanModel.id == user.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        return False, "No plan assigned."

    result = await db.execute(
        select(SignalUsage).where(
            SignalUsage.user_id == user.id,
            SignalUsage.date == date.today()
        )
    )
    usage = result.scalar_one_or_none()

    if not usage:
        usage = SignalUsage(user_id=user.id, count=0)
        db.add(usage)
        await db.commit()
        await db.refresh(usage)

    if usage.count >= plan.max_signals_per_day:
        return False, f"Limit reached ({plan.max_signals_per_day}/day)."

    if user.stake > plan.max_stake:
        return False, f"Stake ${user.stake} exceeds plan limit ${plan.max_stake}."

    usage.count += 1
    await db.commit()
    return True, "OK"


def validate_cycle_risk(user: User, balance: float) -> tuple[bool, str]:
    """
    Validates whether the current stake respects the user's risk mode.
    Safe Mode: stake may not exceed max_cycle_pct of balance.
    Advanced Mode: warns but allows.
    """
    max_allowed = balance * user.max_cycle_pct

    if user.risk_mode == "safe" and user.stake > max_allowed:
        return False, (
            f"[Safe Mode] Stake ${user.stake:.2f} exceeds {user.max_cycle_pct*100:.0f}% "
            f"of your balance (${balance:.2f}). Max allowed: ${max_allowed:.2f}."
        )

    return True, "OK"


def get_cycle_values(user: User) -> list[float]:
    """
    Builds the martingale cycle based on the user's stake and risk_mode.
    Safe Mode:   up to 4 levels.
    Advanced:    up to 6 levels (use with caution).
    """
    levels = SAFE_MAX_MG_LEVELS if user.risk_mode == "safe" else 6
    values = []
    current = user.stake
    for _ in range(levels):
        values.append(round(current, 2))
        current *= 2.2  # standard recovery multiplier
    return values


def next_cycle(user: User, result: str, db) -> float:
    """
    Advances or resets the martingale cycle based on trade result.
    Returns the next stake value.
    """
    cycle_values = get_cycle_values(user)

    if result == "win":
        user.cycle_step = 0
    else:
        user.cycle_step = min(user.cycle_step + 1, len(cycle_values) - 1)

    next_stake = cycle_values[user.cycle_step]
    db.commit()
    return next_stake
