import random

class MockRiskEngine:

    def __init__(self):
        self.win_rate = 0.62
        self.sequence = 0
        self.cycle_level = 1
        self.dd = 0
        self.daily_profit = 0

    def generate_operation(self):
        result = "WIN" if random.random() < self.win_rate else "LOSS"

        if result == "WIN":
            self.sequence = 0
            self.cycle_level = 1
            profit = round(random.uniform(0.5, 2.5), 2)
            self.daily_profit += profit
        else:
            self.sequence += 1
            self.cycle_level = min(self.cycle_level + 1, 6)
            profit = -round(random.uniform(0.5, 2.0), 2)
            self.dd += abs(profit)

        return {
            "result": result,
            "sequence": self.sequence,
            "cycle_level": self.cycle_level,
            "daily_profit": self.daily_profit,
            "drawdown": self.dd
        }
