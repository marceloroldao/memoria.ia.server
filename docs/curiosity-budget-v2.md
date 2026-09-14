# Curiosity budget v2

The curiosity worker reserves a fraction of its hourly request budget for page reads so discovery providers cannot consume the entire allowance before evidence extraction.

Defaults:
- hourly request budget: 120
- read reserve: 40%
- discovery providers may consume at most 60% of the hourly budget
- page reads may use the full remaining budget

When the discovery allowance is exhausted, provider calls emit `discovery_budget_reached` and the worker prefers the Web Walker frontier or waits for the next hour. When the total budget is exhausted, `hourly request budget reached` is emitted.
