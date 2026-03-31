"""Tests for budget tracker."""

from __future__ import annotations

import pytest

from alec.errors import BudgetExhaustedError
from alec.runtime.budget import BudgetTracker


@pytest.mark.asyncio
async def test_record_tokens():
    bt = BudgetTracker(max_tokens=1000)
    await bt.record(100, 50)
    assert bt.tokens_used == 150
    assert bt.tokens_remaining == 850
    assert bt.usage_percent == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_budget_exhausted():
    bt = BudgetTracker(max_tokens=100)
    await bt.record(50, 40)  # 90 tokens, ok
    with pytest.raises(BudgetExhaustedError):
        await bt.record(10, 5)  # 105 tokens, exceeds budget


@pytest.mark.asyncio
async def test_check():
    bt = BudgetTracker(max_tokens=100)
    assert bt.check() is True
    await bt.record(50, 50)
    # At exactly 100, record() doesn't raise (only > max raises)
    # check() returns False when >= max
    assert bt.check() is False


@pytest.mark.asyncio
async def test_summary():
    bt = BudgetTracker(max_tokens=1000)
    await bt.record(100, 200)
    s = bt.summary()
    assert s["tokens_used"] == 300
    assert s["max_tokens"] == 1000
    assert s["tokens_remaining"] == 700
    assert s["usage_percent"] == 30.0


@pytest.mark.asyncio
async def test_zero_budget():
    bt = BudgetTracker(max_tokens=0)
    assert bt.usage_percent == 100.0
    assert bt.check() is False
