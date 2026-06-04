from funnelhub.services.funnel_engine import load_funnel_definition


def test_aisu_email_funnel_definition_uses_course_buttons() -> None:
    definition = load_funnel_definition("content/funnels/aisu_email.yml")

    assert definition.key == "aisu_email_sequence"
    assert len(definition.steps) == 17
    assert definition.steps[0].key == "day_02"
    assert definition.steps[-1].key == "day_18"
    assert all(step.channel == "email" for step in definition.steps)
    assert all(step.delay == "1d" for step in definition.steps)
    assert all(step.buttons for step in definition.steps)
    assert [step.key for step in definition.steps] == [f"day_{day:02d}" for day in range(2, 19)]
    assert {
        button.url
        for step in definition.steps
        for button in step.buttons
    } == {"https://aisukam.ru/courses"}
