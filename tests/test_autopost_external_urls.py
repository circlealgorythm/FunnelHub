from __future__ import annotations

from funnelhub.api.autoposts import build_external_post_url


def test_build_external_post_url_for_vk_publications() -> None:
    assert (
        build_external_post_url(
            channel="vk",
            external_post_id="777",
            vk_owner_id=-211582267,
            vk_personal_owner_id=258149228,
        )
        == "https://vk.com/wall-211582267_777"
    )
    assert (
        build_external_post_url(
            channel="vk_personal",
            external_post_id="777",
            vk_owner_id=-211582267,
            vk_personal_owner_id=258149228,
        )
        == "https://vk.com/id258149228?w=wall258149228_777"
    )
