from decimal import Decimal
from types import SimpleNamespace

import pytest
from protego import Protego

from tracker import fetch
from tracker.alerts import fmt_dt, format_alert
from tracker.fetch import DisallowedByRobots, FetchError, Politeness, RetryableError, with_retries
from tracker.pipeline import decide_status

MYTEK_LIKE = "User-agent: *\nDisallow: /*?\nDisallow: /checkout/\n"


def politeness_with(robots: str) -> Politeness:
    p = Politeness("TestBot/1.0")
    state = p._host("https://shop.example/")[1]
    state.robots = Protego.parse(robots)
    p.set_min_delay("https://shop.example", 0)
    return p


def test_robots_wildcards_are_respected():
    p = politeness_with(MYTEK_LIKE)
    p.check_and_wait("https://shop.example/pc-portable.html")
    with pytest.raises(DisallowedByRobots):
        p.check_and_wait("https://shop.example/pc-portable.html?p=2")
    assert p.stats["shop.example"].blocked_by_robots == 1


def test_retries_then_success(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    p = politeness_with("")
    calls = iter([RetryableError("HTTP 503"), RetryableError("timeout"), "<html>ok</html>"])

    def flaky():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    assert with_retries(p, "https://shop.example/x", flaky) == "<html>ok</html>"
    assert p.stats["shop.example"].retries == 2 and p.stats["shop.example"].pages == 1


def test_retries_give_up(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    p = politeness_with("")

    def always_down():
        raise RetryableError("HTTP 503")

    with pytest.raises(FetchError):
        with_retries(p, "https://shop.example/x", always_down)
    assert p.stats["shop.example"].failures == 1


def test_permanent_errors_are_not_retried():
    p = politeness_with("")
    calls = []

    def not_found():
        calls.append(1)
        raise FetchError("HTTP 404")

    with pytest.raises(FetchError):
        with_retries(p, "https://shop.example/x", not_found)
    assert len(calls) == 1


def test_alert_message():
    row = SimpleNamespace(site="spacenet", name="PC <Demo> 8Go", url="https://x/1", group_id=7,
                          old_price=Decimal("1500"), new_price=Decimal("1290"), drop_pct=Decimal("14.00"))
    text = format_alert([row], {7: [("spacenet", 1290.0), ("tunisianet", 1350.0)]})
    assert "1 500,000 → <b>1 290,000 DT</b>" in text
    assert "&lt;Demo&gt;" in text  # HTML-escaped for Telegram
    assert "Tunisianet : 1 350,000 DT (désormais le moins cher)" in text
    assert fmt_dt(1234567.5) == "1 234 567,500"


def test_status_detection():
    ok = {"a": {"products": 100, "errors": []}, "b": {"products": 90, "errors": []}}
    assert decide_status(ok, {"a": 100, "b": 95})[0] == "ok"
    shrunk = {"a": {"products": 30, "errors": []}, "b": {"products": 90, "errors": []}}
    status, warnings = decide_status(shrunk, {"a": 100})
    assert status == "degraded" and "a: 30 produits" in warnings[0]
    dead = {"a": {"products": 0, "errors": ["x"]}}
    assert decide_status(dead, {})[0] == "failed"


def test_bot_challenge_stops_the_site(monkeypatch):
    """After a bot check, no further category of that site is requested."""
    from tracker import pipeline
    from tracker.fetch import BotChallenge

    requested = []

    class FakeFetcher:
        def __init__(self, p):
            pass

        def get(self, url):
            requested.append(url)
            raise BotChallenge("challenge")

    monkeypatch.setattr(pipeline, "HttpFetcher", FakeFetcher)
    cfg = {"base_url": "https://shop.example", "engine": "http", "min_delay_s": 0,
           "categories": [{"name": "A", "url": "https://shop.example/a"},
                          {"name": "B", "url": "https://shop.example/b"}]}
    result = pipeline.scrape_site("tunisianet", cfg, Politeness("TestBot"), None)
    assert requested == ["https://shop.example/a"]
    assert result["errors"] == ["challenge"] and result["listings"] == []


def test_email_report(monkeypatch, tmp_path):
    from tracker import notify
    from tracker.config import settings

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.test", 587)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, context): pass
        def login(self, user, password): assert (user, password) == ("me@test", "secret")
        def send_message(self, msg): sent.append(msg)

    for k, v in {"smtp_host": "smtp.test", "smtp_port": 587, "smtp_user": "me@test",
                 "smtp_password": "secret", "email_to": ["a@test", "b@test"],
                 "telegram_token": ""}.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    xlsx = tmp_path / "prix.xlsx"
    xlsx.write_bytes(b"PK fake")

    assert notify.send('<b>Relevé OK</b> &gt; 10%\n<a href="https://x/1">voir</a>', "Sujet", [xlsx])
    msg = sent[0]
    assert msg["To"] == "a@test, b@test" and msg["Subject"] == "Sujet"
    assert msg.get_body(("plain",)).get_content().strip() == "Relevé OK > 10%\nvoir: https://x/1"
    assert [a.get_filename() for a in msg.iter_attachments()] == ["prix.xlsx"]


def test_bot_check_is_not_reported_as_html_change():
    blocked = {"a": {"products": 40, "errors": ["www.a.tn served a bot check page; stopping this site for today"]}}
    status, warnings = decide_status(blocked, {"a": 100})
    assert status == "degraded" and "anti-bot" in warnings[0] and "structure" not in warnings[0]
