from funnelhub.db import models  # noqa: F401
from funnelhub.db.base import Base


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "leads",
        "lead_contacts",
        "lead_external_ids",
        "lead_utm",
        "lead_custom_fields",
        "lead_consents",
        "messenger_identities",
        "bot_link_tokens",
        "email_subscriptions",
        "funnel_states",
        "conversations",
        "messages",
        "import_batches",
        "import_rows",
        "events",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())
