"""Provider fallback: a model that fails, is empty, or leaks its raw reasoning is skipped and the next one answers."""
import json

import pytest

from instonct import brain, core, llm


class Resp:
    def __init__(self, status=200, content="ok", raw=None):
        self.status_code = status
        self.text = raw if raw is not None else json.dumps({"choices": [{"message": {"content": content}}]})

    def json(self):
        return json.loads(self.text)


class FakeNet:
    """Answers by model name, and records the order in which models were tried."""
    def __init__(self, answers):
        self.answers, self.tried = answers, []

    def post(self, url, json=None, **kw):
        self.tried.append(json["model"])
        return self.answers[json["model"]]


@pytest.fixture
def net(monkeypatch):
    def install(answers):
        fake = FakeNet(answers)
        monkeypatch.setattr(llm, "NET", fake)
        return fake
    return install


def call():
    return llm.llm_call([{"role": "user", "content": "salut"}], "salut", False)


def models():
    return llm.llm_models()


def test_first_model_answers(net):
    fake = net({m: Resp(content="bonjour") for m in models()})
    assert call().json()["choices"][0]["message"]["content"] == "bonjour"
    assert fake.tried == models()[:1]


def test_rate_limited_model_is_skipped_and_cooled_down(net):
    first, second = models()[:2]
    fake = net({**{m: Resp(content="ok") for m in models()}, first: Resp(429, raw="Rate limit. Please try again in 2h3m1.5s")})
    assert call() is not None
    assert fake.tried[:2] == [first, second]
    assert 3500 < core.db.ttl(f"cool:{first}") <= 3600       # capped at one hour


def test_leaked_reasoning_is_never_returned(net):
    first = models()[0]
    leak = json.dumps({"choices": [{"message": {"content": "<|channel|>analysis<|message|>je reflechis"}}]})
    net({**{m: Resp(content="propre") for m in models()}, first: Resp(raw=leak)})
    assert call().json()["choices"][0]["message"]["content"] == "propre"
    assert core.db.get(f"cool:{first}")


def test_escaped_leak_is_caught_too(net):
    first = models()[0]
    net({**{m: Resp(content="propre") for m in models()}, first: Resp(raw='{"choices":[{"message":{"content":"\\u003c|channel|\\u003eanalysis"}}]}')})
    assert call().json()["choices"][0]["message"]["content"] == "propre"


def test_empty_answer_moves_on(net):
    first = models()[0]
    net({**{m: Resp(content="reponse") for m in models()}, first: Resp(content="   ")})
    assert call().json()["choices"][0]["message"]["content"] == "reponse"


def test_leaked_answers_are_not_stored_in_history():
    brain.remember(42, "question", "<|channel|>analysis<|message|>brouillon")
    assert not core.db.exists("hist:42")


def test_normal_answers_are_stored_in_history():
    brain.remember(42, "question", "reponse")
    assert core.db.exists("hist:42")


def test_markers_in_hidden_reasoning_do_not_skip_a_good_model(net):
    first = models()[0]
    raw = json.dumps({"choices": [{"message": {"content": "bonjour", "reasoning": "<|channel|>analysis<|message|>je reflechis"}}]})
    fake = net({**{m: Resp(content="autre") for m in models()}, first: Resp(raw=raw)})
    assert call().json()["choices"][0]["message"]["content"] == "bonjour"
    assert fake.tried == [first] and not core.db.get(f"cool:{first}")


def test_markers_in_tool_arguments_are_caught(net):
    first = models()[0]
    raw = json.dumps({"choices": [{"message": {"tool_calls": [{"function": {"name": "x", "arguments": "<|call|>"}}]}}]})
    net({**{m: Resp(content="propre") for m in models()}, first: Resp(raw=raw)})
    assert call().json()["choices"][0]["message"]["content"] == "propre"


def test_strong_models_come_first_whatever_the_provider():
    order = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "@cf/openai/gpt-oss-120b", "@cf/openai/gpt-oss-20b", "gpt-oss-120b"]
    assert sorted(order, key=lambda m: ("120b" not in m, m.startswith("@cf/"))) == [
        "openai/gpt-oss-120b", "gpt-oss-120b", "@cf/openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "@cf/openai/gpt-oss-20b"]
