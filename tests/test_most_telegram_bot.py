from funnelhub.config import Settings
from funnelhub.most_telegram_bot import MOST_FUNNEL_KEY, QUIZ, quiz_result
from funnelhub.services.funnel_engine import load_funnel_definition


def test_most_funnel_definition_is_valid() -> None:
    definition = load_funnel_definition("content/funnels/most_tsennostey.yml")

    assert definition.key == MOST_FUNNEL_KEY
    assert definition.steps[0].channel == "telegram_most"
    assert {step.key for step in definition.steps} >= {
        "quiz_invite",
        "lesson",
        "day_2_practice",
        "day_3_polarities",
        "day_5_invitation",
        "closing",
    }
    assert definition.steps[1].delay == "1m"
    assert "Это не марафон исполнения желаний" in definition.steps[1].text
    assert definition.steps[definition.step_index("lesson")].delay == "1h"
    assert "Пройти тест" in [
        button.text for button in definition.steps[definition.step_index("reflection")].buttons
    ]
    polarities_step = definition.steps[definition.step_index("day_3_polarities")]
    assert "Готово" in [button.text for button in polarities_step.buttons]


def test_quiz_answers_are_transport_safe_callbacks() -> None:
    assert len(QUIZ) == 5
    assert all(len(f"fh_answer:q{index}-0".encode()) <= 64 for index in range(len(QUIZ)))


def test_quiz_result_returns_single_and_mixed_outcomes() -> None:
    assert quiz_result({"внешняя безопасность": 5, "контроль и результат": 2}) == (
        "внешняя безопасность"
    )
    assert quiz_result({"внешняя безопасность": 3, "контроль и результат": 3}) == (
        "несколько внутренних опор"
    )
    assert quiz_result({"внешняя безопасность": 3, "контроль и результат": 2}) == (
        "несколько внутренних опор"
    )


def test_most_bot_settings_are_optional_until_the_service_starts() -> None:
    settings = Settings(most_telegram_bot_token=None, most_telegram_bot_username=None)

    assert settings.most_telegram_bot_token is None
    assert settings.most_telegram_bot_username is None
