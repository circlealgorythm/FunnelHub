from pathlib import Path


def test_caddyfile_security_configuration() -> None:
    caddyfile_path = Path(__file__).resolve().parents[1] / "Caddyfile"
    assert caddyfile_path.exists(), "Caddyfile must exist in repository root"

    content = caddyfile_path.read_text(encoding="utf-8")

    # Domain check
    assert "bot.aisukam.ru" in content

    # Reverse proxy intact
    assert "reverse_proxy 127.0.0.1:8000" in content

    # Request body limit
    assert "request_body" in content
    assert "max_size 15MB" in content

    # Security headers
    assert "Strict-Transport-Security" in content
    assert "max-age=31536000" in content
    assert "X-Content-Type-Options" in content
    assert "nosniff" in content
    assert "X-Frame-Options" in content
    assert "SAMEORIGIN" in content
    assert "Referrer-Policy" in content
    assert "Permissions-Policy" in content
    assert "Content-Security-Policy" in content
    assert "-Server" in content

    # Braces balancing check
    open_braces = content.count("{")
    close_braces = content.count("}")
    assert (
        open_braces == close_braces
    ), f"Mismatched braces in Caddyfile: {open_braces} != {close_braces}"
