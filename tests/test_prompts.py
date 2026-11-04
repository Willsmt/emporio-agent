from datetime import datetime

from emporio.agent.prompts import build_system_prompt, next_opening, store_open_status


def test_store_open_on_weekday_business_hours():
    assert store_open_status(datetime(2026, 11, 3, 10, 0)).startswith("OPEN")


def test_store_closed_saturday_afternoon_and_sunday():
    assert store_open_status(datetime(2026, 11, 7, 14, 0)).startswith("CLOSED")
    assert store_open_status(datetime(2026, 11, 8, 10, 0)).startswith("CLOSED")


def test_prompt_includes_current_context():
    prompt = build_system_prompt(datetime(2026, 11, 3, 10, 30))
    assert "terça-feira, 03/11/2026 10:30" in prompt


def test_next_opening_after_weekday_closing():
    assert next_opening(datetime(2026, 11, 3, 22, 37)) == datetime(2026, 11, 4, 9, 0)


def test_next_opening_skips_sunday():
    assert next_opening(datetime(2026, 11, 7, 14, 0)) == datetime(2026, 11, 9, 9, 0)


def test_closed_status_tells_when_team_returns():
    status = store_open_status(datetime(2026, 11, 3, 22, 37))
    assert '"amanhã, quarta-feira (04/11), às 09:00"' in status


def test_closed_after_midnight_reopens_today():
    # Friday 00:17: the team is back the same day, not "tomorrow"
    assert '"hoje, sexta-feira (20/02), às 09:00"' in store_open_status(datetime(2026, 2, 20, 0, 17))


def test_closed_on_saturday_afternoon_names_monday_without_relative_word():
    assert '"segunda-feira (09/11), às 09:00"' in store_open_status(datetime(2026, 11, 7, 14, 0))


def test_prompt_requires_payment_conditions_for_a_specific_product():
    prompt = build_system_prompt(datetime(2026, 11, 3, 10, 30))
    assert "call get_product" in prompt and "PIX price" in prompt
