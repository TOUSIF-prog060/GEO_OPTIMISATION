import json
from types import SimpleNamespace

import httpx
import pytest

from src.config import ProviderConfig
from src.discovery.providers import (
    ask_openai,
    ask_perplexity,
    estimate_cost,
    get_ask_fn,
    parse_openai,
    parse_perplexity,
)

PPLX_RAW = {
    "model": "sonar",
    "choices": [{"message": {"content": "Try Nykaa or Sephora India."}}],
    "citations": ["https://nykaa.com/a", "https://sephora.in/b", "https://nykaa.com/a"],
    "usage": {"prompt_tokens": 12, "completion_tokens": 30},
}

OPENAI_RAW = {
    "model": "gpt-5-mini",
    "output": [
        {"type": "web_search_call", "status": "completed"},
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "Tira has good offers.",
                    "annotations": [
                        {"type": "url_citation", "url": "https://tirabeauty.com/x"},
                        {"type": "url_citation", "url": "https://tirabeauty.com/x"},
                    ],
                }
            ],
        },
    ],
    "usage": {"input_tokens": 50, "output_tokens": 20},
}


@pytest.fixture
def pplx_cfg() -> ProviderConfig:
    return ProviderConfig(
        name="perplexity",
        model="sonar",
        price_input_per_mtok=1.0,
        price_output_per_mtok=1.0,
        price_per_request=0.005,
    )


def test_parse_perplexity_dedupes_citations() -> None:
    answer, cites, tin, tout = parse_perplexity(PPLX_RAW)
    assert answer.startswith("Try Nykaa")
    assert cites == ["https://nykaa.com/a", "https://sephora.in/b"]
    assert (tin, tout) == (12, 30)


def test_parse_perplexity_falls_back_to_search_results() -> None:
    raw = {**PPLX_RAW, "citations": None, "search_results": [{"url": "https://x.com"}, {}]}
    assert parse_perplexity(raw)[1] == ["https://x.com"]


def test_parse_openai_extracts_text_and_citations() -> None:
    answer, cites, tin, tout = parse_openai(OPENAI_RAW)
    assert answer == "Tira has good offers."
    assert cites == ["https://tirabeauty.com/x"]
    assert (tin, tout) == (50, 20)


def test_estimate_cost(pplx_cfg: ProviderConfig) -> None:
    assert estimate_cost(pplx_cfg, 1_000_000, 0) == pytest.approx(1.005)
    assert estimate_cost(ProviderConfig(name="x", model="m"), 100, 100) is None


def test_ask_perplexity_with_mock_transport(pplx_cfg: ProviderConfig) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=PPLX_RAW)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ans = ask_perplexity(pplx_cfg, "secret-key", "best sunscreen?", client=client)

    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["messages"][0]["content"] == "best sunscreen?"
    assert ans.raw == PPLX_RAW  # stored untouched
    assert "secret-key" not in json.dumps(ans.request)  # key never stored
    assert ans.citations == ["https://nykaa.com/a", "https://sephora.in/b"]
    assert ans.cost_usd is not None and ans.http_status == 200


def test_ask_perplexity_raises_on_http_error(pplx_cfg: ProviderConfig) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(httpx.HTTPStatusError):
        ask_perplexity(pplx_cfg, "k", "q", client=client)


def test_ask_openai_with_fake_client() -> None:
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(model_dump=lambda mode=None: OPENAI_RAW)

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    cfg = ProviderConfig(name="openai", model="gpt-5-mini")
    ans = ask_openai(cfg, "k", "where to buy perfume?", client=fake)

    assert calls["tools"] == [{"type": "web_search"}]
    assert calls["input"] == "where to buy perfume?"
    assert ans.answer_text == "Tira has good offers."
    assert ans.cost_usd is None  # prices not configured


def test_unknown_provider() -> None:
    with pytest.raises(KeyError):
        get_ask_fn("nope")
