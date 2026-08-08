from funnelhub.config import Settings
from funnelhub.most_telegram_bot import (
    BUTTON_REPLIES,
    MOST_FUNNEL_KEY,
    QUIZ,
    can_start_most_quiz,
    load_most_vk_definition,
    quiz_result,
    resolve_funnel_button_value,
    resolve_quiz_option_value,
    should_notify_about_tag_by_email,
)
from funnelhub.most_vk_bot import MOST_VK_CHANNEL, MOST_VK_FUNNEL_KEY
from funnelhub.services.funnel_engine import load_funnel_definition


def test_most_funnel_definition_is_valid() -> None:
    definition = load_funnel_definition("content/funnels/most_tsennostey.yml")

    assert definition.key == MOST_FUNNEL_KEY
    assert definition.calendar_day_schedule is True
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
    assert [
        button.text
        for step in definition.steps
        for button in step.buttons
        if button.text == "Пройти тест"
    ] == ["Пройти тест"]
    assert [
        button.text
        for button in definition.steps[definition.step_index("quiz_invite")].buttons
    ] == ["Пройти тест"]
    polarities_step = definition.steps[definition.step_index("day_3_polarities")]
    assert "Готово" in [button.text for button in polarities_step.buttons]
    practice_step = definition.steps[definition.step_index("day_2_practice")]
    assert "Запишите письменно на листочке (в боте писать не надо)" in practice_step.text


def test_most_funnel_timing_matches_the_scenario() -> None:
    definition = load_funnel_definition("content/funnels/most_tsennostey.yml")

    assert [(step.key, step.delay) for step in definition.steps] == [
        ("day_1_welcome", "0m"),
        ("day_1_about", "1m"),
        ("day_1_leader", "1m"),
        ("day_1_context", "1m"),
        ("quiz_invite", "1m"),
        ("lesson", "1h"),
        ("reflection", "30m"),
        ("day_2_practice", "1d"),
        ("day_3_polarities", "1d"),
        ("day_4_values", "1d"),
        ("day_5_invitation", "1d"),
        ("day_6_objections", "1d"),
        ("day_8_reminder", "2d"),
        ("closing", "1d"),
    ]


def test_quiz_answers_are_transport_safe_callbacks() -> None:
    assert len(QUIZ) == 5
    assert all(len(f"fh_answer:q{index}-0".encode()) <= 64 for index in range(len(QUIZ)))


def test_most_funnel_buttons_are_transport_safe_callbacks() -> None:
    definition = load_funnel_definition("content/funnels/most_tsennostey.yml")

    assert all(
        len(f"fh_answer:{button.callback_data or button.text}".encode()) <= 64
        for step in definition.steps
        for button in step.buttons
    )


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


def test_most_vk_text_buttons_resolve_to_the_same_actions_as_telegram_callbacks() -> None:
    definition = load_most_vk_definition(Settings())
    price_text = next(
        button.text
        for step in definition.steps
        for button in step.buttons
        if button.callback_data == "price"
    )

    assert resolve_funnel_button_value(definition, price_text) == "price"
    assert resolve_quiz_option_value(QUIZ[0].options[2].text, 0) == "q0-2"
    assert (
        resolve_funnel_button_value(definition, "Я зацикливаюсь на деньгах")
        == "reflection_money"
    )


def test_completed_quiz_cannot_be_started_again_from_an_old_button() -> None:
    assert can_start_most_quiz({})
    assert not can_start_most_quiz({"most_quiz_result": "внешняя безопасность"})


def test_only_application_choice_tags_notify_by_email() -> None:
    assert should_notify_about_tag_by_email("заявка")
    assert should_notify_about_tag_by_email("занять место")
    assert should_notify_about_tag_by_email("онлайн-формат")
    assert not should_notify_about_tag_by_email("результат теста: внешняя безопасность")
    assert not should_notify_about_tag_by_email("зависимость от реакции людей")


def test_practice_completion_mentions_tomorrows_resource_topic() -> None:
    reply_text = BUTTON_REPLIES["Я заполнил(а) практику"][1]

    assert "следующий раз я замечу ______ и перед действием сделаю ______»" in reply_text
    assert "Завтра мы разберем, какие внутренние ресурсы" in reply_text
