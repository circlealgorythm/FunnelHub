from funnelhub.config import Settings
from funnelhub.most_telegram_bot import (
    MOST_FUNNEL_KEY,
    QUIZ,
    load_most_vk_definition,
    quiz_result,
)
from funnelhub.most_vk_bot import MOST_VK_CHANNEL, MOST_VK_FUNNEL_KEY
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


def test_most_vk_reuses_the_full_script_with_an_isolated_channel() -> None:
    definition = load_most_vk_definition(Settings())
    telegram_definition = load_funnel_definition("content/funnels/most_tsennostey.yml")

    assert definition.key == MOST_VK_FUNNEL_KEY
    assert all(step.channel == "messenger" for step in definition.steps)
    vk_practice_text = definition.steps[definition.step_index("day_2_practice")].text
    telegram_practice_text = telegram_definition.steps[
        telegram_definition.step_index("day_2_practice")
    ].text
    assert vk_practice_text == telegram_practice_text
    assert MOST_VK_CHANNEL == "vk_most"


def test_most_vk_settings_normalize_the_group_id() -> None:
    settings = Settings(most_vk_group_id="club240711612")

    assert settings.most_vk_group_id == 240711612
