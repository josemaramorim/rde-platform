"""
AI Engine – detects profitable and at-risk users.
Uses a simple logistic regression model trained on per-session data.
Replace with a more sophisticated model as data grows.
"""
import logging

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

logger = logging.getLogger("rde")


def _build_features(users: list) -> list:
    """Extract feature vectors from user records."""
    return [[u.total_profit, u.cycle_step, u.stake] for u in users]


def detect_profitable_users(users: list) -> list[str]:
    """
    Returns a list of emails of users whose total_profit > $100.
    Falls back to simple threshold if sklearn is unavailable.
    """
    if not users:
        return []

    if not _ML_AVAILABLE:
        # Simple fallback
        return [u.email for u in users if u.total_profit > 100]

    X = _build_features(users)
    y = [1 if u.total_profit > 100 else 0 for u in users]

    if len(set(y)) < 2:
        # All same class – can't train
        return [u.email for u in users if u.total_profit > 100]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression()
    model.fit(X_scaled, y)
    predictions = model.predict(X_scaled)

    return [users[i].email for i, pred in enumerate(predictions) if pred == 1]


def detect_at_risk_users(users: list) -> list[str]:
    """
    Returns emails of users who are at risk (negative profit or high cycle_step).
    """
    return [
        u.email
        for u in users
        if u.total_profit < 0 or u.cycle_step >= 3
    ]


def user_risk_score(user) -> float:
    """
    Returns a normalised risk score [0.0 – 1.0].
    Higher = more at risk.
    """
    score = 0.0
    if user.total_profit < 0:
        score += 0.5
    if user.cycle_step >= 3:
        score += 0.3
    if user.risk_mode == "advanced":
        score += 0.2
    return min(score, 1.0)
