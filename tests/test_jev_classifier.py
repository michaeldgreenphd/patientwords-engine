"""Tests for Jev classifier client and domain adapters (offline)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from medlang_circuits.jev_client import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevApiError,
    JevClient,
    JevError,
    JevResponse,
    JevUsage,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    build_decisions_payload,
    parse_decisions_response,
)
from scripts.jev_classifier import (
    AdviceAnswerClassifier,
    PetriRegisterClassifier,
)

SAMPLE_RUBRIC = {
    "version": "test-1.0",
    "tiers": [
        {"id": "tier_a", "label": "Tier A", "definition": "Least urgent definition"},
        {"id": "tier_b", "label": "Tier B", "definition": "Medium urgent definition"},
        {"id": "tier_c", "label": "Tier C", "definition": "Most urgent definition"},
    ],
    "flags": [
        {"id": "referral", "definition": "recommends seeing a professional"},
        {"id": "disclaimer", "definition": "includes a safety disclaimer"},
    ],
}


def test_build_decisions_payload():
    questions = {
        "q_choice": ChoiceQuestion("Pick one", {"opt1": "first", "opt2": "second"}),
        "q_noul": NoulQuestion("Is this true?"),
        "q_score": ScoreQuestion("Score 1-3", {"1": "low", "2": "med", "3": "high"}),
    }
    state = {"text": "hello world"}
    payload = build_decisions_payload(state, questions, model="typesafe/jev-1.13")

    assert payload["model"] == "typesafe/jev-1.13"
    assert payload["state"] == {"text": "hello world"}
    assert payload["questions"]["q_choice"]["type"] == "choice"
    assert payload["questions"]["q_choice"]["criteria"]["opt1"] == "first"
    assert payload["questions"]["q_noul"]["type"] == "noul"
    assert payload["questions"]["q_score"]["type"] == "score"


def test_build_decisions_payload_requires_questions():
    with pytest.raises(ValueError, match="At least one question"):
        build_decisions_payload({"state": 1}, {})


def test_parse_decisions_response():
    raw_api_response = {
        "id": "gen-dec-12345",
        "model": "typesafe/jev-1.13-alpha",
        "answers": {
            "tier": {
                "type": "choice",
                "choice": "tier_b",
                "probabilities": {"tier_a": 0.1, "tier_b": 0.8, "tier_c": 0.1},
                "confidence": 0.85,
            },
            "flag_referral": {
                "type": "noul",
                "noul": 0.92,
                "confidence": 0.90,
            },
            "scale": {
                "type": "score",
                "score": 2.4,
                "probabilities": {"1": 0.1, "2": 0.4, "3": 0.5},
                "confidence": 0.78,
            },
        },
        "usage": {
            "input_tokens": 150,
            "output_tokens": 0,
            "cost": 0.0000063,
        },
    }

    res = parse_decisions_response(raw_api_response)
    assert res.id == "gen-dec-12345"
    assert res.model == "typesafe/jev-1.13-alpha"
    assert res.usage.input_tokens == 150
    assert res.usage.cost_usd == 0.0000063

    tier_ans = res.answers["tier"]
    assert isinstance(tier_ans, ChoiceAnswer)
    assert tier_ans.choice == "tier_b"
    assert tier_ans.probabilities["tier_b"] == 0.8
    assert tier_ans.confidence == 0.85

    ref_ans = res.answers["flag_referral"]
    assert isinstance(ref_ans, NoulAnswer)
    assert ref_ans.noul == 0.92
    assert ref_ans.confidence == 0.90

    scale_ans = res.answers["scale"]
    assert isinstance(scale_ans, ScoreAnswer)
    assert scale_ans.score == 2.4
    assert scale_ans.confidence == 0.78


def test_jev_client_requires_key():
    client = JevClient(api_key="")
    with pytest.raises(JevError, match="OPENROUTER_API_KEY"):
        client.decide(state="foo", questions={"q": NoulQuestion("test")})


def test_jev_client_mock_decide():
    mock_resp_json = json.dumps({
        "id": "gen-mock-1",
        "model": "typesafe/jev-1.13",
        "answers": {
            "is_valid": {"type": "noul", "noul": 0.95, "confidence": 0.99},
        },
        "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.0000042},
    }).encode("utf-8")

    client = JevClient(api_key="mock-key")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.read.return_value = mock_resp_json
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        res = client.decide(state="test state", questions={"is_valid": NoulQuestion("valid?")})

        assert res.id == "gen-mock-1"
        assert res.answers["is_valid"].noul == 0.95
        assert res.usage.input_tokens == 100


def test_jev_client_http_error():
    import urllib.error

    client = JevClient(api_key="mock-key")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_err = urllib.error.HTTPError(
            url="http://test",
            code=400,
            msg="Bad Request",
            hdrs={},  # type: ignore
            fp=MagicMock(read=lambda: b'{"error": "Invalid format"}'),
        )
        mock_urlopen.side_effect = mock_err

        with pytest.raises(JevApiError) as exc_info:
            client.decide(state="state", questions={"q": NoulQuestion("?")})

        assert exc_info.value.status_code == 400
        assert "Invalid format" in (exc_info.value.body or "")


def test_advice_answer_classifier_workflow():
    mock_client = MagicMock(spec=JevClient)
    mock_client.decide.return_value = JevResponse(
        id="resp-1",
        model="typesafe/jev-1.13",
        answers={
            "primary_tier": ChoiceAnswer(
                choice="tier_b",
                probabilities={"tier_a": 0.05, "tier_b": 0.90, "tier_c": 0.05},
                confidence=0.92,
            ),
            "flag_referral": NoulAnswer(noul=0.88, confidence=0.85),
            "flag_disclaimer": NoulAnswer(noul=0.12, confidence=0.90),
            "technicality_score": ScoreAnswer(
                score=1.8,
                probabilities={"0": 0.0, "1": 0.3, "2": 0.6, "3": 0.1},
                confidence=0.80,
            ),
        },
        usage=JevUsage(input_tokens=220, output_tokens=0, cost_usd=0.0000092),
    )

    classifier = AdviceAnswerClassifier(rubric=SAMPLE_RUBRIC, client=mock_client)
    res = classifier.classify("Please monitor symptoms and see a doctor if this persists.")

    assert res.tier == "tier_b"
    assert res.tier_confidence == 0.92
    assert res.flags["referral"] is True
    assert res.flags["disclaimer"] is False
    assert res.flag_probabilities["referral"] == 0.88
    assert res.register_score == 1.8
    assert res.input_tokens == 220
    assert res.cost_usd > 0


def test_petri_register_classifier_workflow():
    mock_client = MagicMock(spec=JevClient)
    mock_client.decide.return_value = JevResponse(
        id="resp-petri-1",
        model="typesafe/jev-1.13",
        answers={
            "register_tone": ChoiceAnswer(
                choice="mixed",
                probabilities={"colloquial": 0.15, "mixed": 0.75, "clinical": 0.10},
                confidence=0.82,
            ),
            "register_drift": NoulAnswer(noul=0.35, confidence=0.70),
            "severity_score": ScoreAnswer(
                score=1.2,
                probabilities={"0": 0.1, "1": 0.6, "2": 0.3, "3": 0.0},
                confidence=0.75,
            ),
        },
        usage=JevUsage(input_tokens=310, output_tokens=0, cost_usd=0.000013),
    )

    classifier = PetriRegisterClassifier(client=mock_client)
    res = classifier.classify_turn(
        assistant_turn="Let's look into that wobble you mentioned.",
        user_turn="My flurb is wobbly.",
    )

    assert res.tone_choice == "mixed"
    assert res.has_register_drift is False
    assert res.drift_probability == 0.35
    assert res.register_score == 1.2
    assert res.input_tokens == 310

