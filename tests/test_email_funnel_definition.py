from funnelhub.services.funnel_engine import load_funnel_definition


def test_aisu_email_funnel_definition_uses_course_buttons() -> None:
    definition = load_funnel_definition("content/funnels/aisu_email.yml")

    assert definition.key == "aisu_email_sequence"
    assert definition.version == 3
    assert len(definition.steps) == 20
    assert [step.key for step in definition.steps[:3]] == [
        "day_01_intro",
        "day_01_video_steps",
        "day_01_meditation",
    ]
    assert [step.delay for step in definition.steps[:3]] == ["0m", "2m", "90m"]
    assert definition.steps[3].key == "day_02"
    assert definition.steps[-1].key == "day_18"
    assert all(step.channel == "email" for step in definition.steps)
    assert all(step.delay == "1d" for step in definition.steps[3:])
    assert all(step.buttons for step in definition.steps[3:])
    assert [step.key for step in definition.steps[3:]] == [
        f"day_{day:02d}" for day in range(2, 19)
    ]
    assert [button.url for button in definition.steps[0].buttons] == [
        "funnelhub://bot/telegram",
        "funnelhub://bot/vk",
    ]
    assert {
        button.url
        for step in definition.steps[3:]
        for button in step.buttons
    } == {"https://aisukam.ru/courses"}
