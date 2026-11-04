from datetime import datetime

from emporio.agent.prompts import build_system_prompt, store_open_status


def test_store_open_on_weekday_business_hours():
    assert store_open_status(datetime(2026, 11, 3, 10, 0)).startswith("OPEN")


def test_store_closed_saturday_afternoon_and_sunday():
    assert store_open_status(datetime(2026, 11, 7, 14, 0)).startswith("CLOSED")
    assert store_open_status(datetime(2026, 11, 8, 10, 0)).startswith("CLOSED")


def test_prompt_includes_current_context():
    prompt = build_system_prompt(datetime(2026, 11, 3, 10, 30))
    assert "terça-feira, 03/11/2026 10:30" in prompt
