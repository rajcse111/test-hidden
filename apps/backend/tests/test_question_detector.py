import time

import pytest

from app.services.question_detector import DetectionResult, QuestionDetector


def _d(**overrides) -> QuestionDetector:
    defaults = dict(
        confidence_threshold=0.6,
        min_words=4,
        topic_shift_min_words=6,
        dedup_window_seconds=30.0,
        similarity_threshold=0.85,
        cooldown_seconds=0.0,  # disabled so tests don't depend on wall clock
    )
    return QuestionDetector(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Basic question detection
# ---------------------------------------------------------------------------

def test_wh_question_detected():
    r = _d().detect("What is the time complexity of quicksort?")
    assert r.detected is True
    assert r.kind == "question"
    assert r.confidence >= 0.6


def test_aux_inversion_detected():
    r = _d().detect("Can you explain how binary search works here?")
    assert r.detected is True
    assert r.kind == "question"


def test_how_question_detected():
    r = _d().detect("How does garbage collection work in Java at runtime?")
    assert r.detected is True
    assert r.kind == "question"


def test_statement_not_detected():
    r = _d().detect("I have worked with Python for five years now and really enjoy it.")
    assert r.detected is False


def test_short_utterance_rejected():
    # 2 words < min_words=4
    r = _d().detect("What now")
    assert r.detected is False


# ---------------------------------------------------------------------------
# Topic shift detection
# ---------------------------------------------------------------------------

def test_topic_shift_explain_detected():
    r = _d().detect("Explain the CAP theorem and its trade-offs in distributed systems.")
    assert r.detected is True
    assert r.kind in ("question", "topic_shift")


def test_topic_shift_tell_me_about_detected():
    r = _d().detect("Tell me about your experience with microservices architecture overall.")
    assert r.detected is True


def test_topic_shift_short_rejected():
    # "Explain now" = 2 words < topic_shift_min_words=6, base kind=topic_shift
    r = _d().detect("Explain something now")  # 3 words < 6
    assert r.detected is False


def test_topic_shift_long_enough():
    r = _d().detect("Walk me through your experience with distributed system design.")
    assert r.detected is True


# ---------------------------------------------------------------------------
# Confidence threshold
# ---------------------------------------------------------------------------

def test_high_threshold_suppresses_wh_question():
    # WH scores 0.9+0.1=1.0 with "?", but let's use a text without "?" so base=0.9
    r = _d(confidence_threshold=0.95).detect("What is the time complexity of merge sort algorithm")
    # score is 0.9 (no trailing ?) which is < 0.95
    assert r.detected is False


def test_low_threshold_allows_topic_shift():
    r = _d(confidence_threshold=0.5).detect("Tell me about your background and journey into software.")
    assert r.detected is True


def test_question_mark_boost_applies():
    # WH + "?" → 0.9 + 0.1 = 1.0, well over default 0.6
    r = _d().detect("How does garbage collection work in Java?")
    assert r.detected is True
    assert r.confidence >= 0.9


def test_question_mark_only_below_default_threshold():
    # Pure "?" with no WH or aux: base=0.55, +0.1=0.65 > 0.6 — just over threshold
    # "Did the server crash again right now?" — aux inversion "Did" scores 0.85
    # Use a truly bare question-mark sentence with filler words
    r = _d(confidence_threshold=0.7).detect("The server went down right now?")
    # base=0.55 (only ?) + 0.1 boost = 0.65 < 0.7
    assert r.detected is False


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_dedup_suppresses_identical():
    d = _d()
    d.detect("What is your greatest weakness in your current role?")
    r2 = d.detect("What is your greatest weakness in your current role?")
    assert r2.detected is False


def test_dedup_suppresses_high_overlap_paraphrase():
    d = _d()
    d.detect("What is your biggest weakness at work in this role?")
    # High Jaccard overlap with "weakness work role biggest" etc.
    r2 = d.detect("What is your biggest weakness at work in this role today?")
    assert r2.detected is False


def test_dedup_allows_different_question():
    d = _d()
    d.detect("What is your greatest strength as an engineer?")
    r2 = d.detect("How do you handle conflict with a difficult colleague?")
    assert r2.detected is True


def test_dedup_expires_after_window():
    d = _d(dedup_window_seconds=0.01)
    d.detect("What is the difference between TCP and UDP protocols?")
    time.sleep(0.02)
    r2 = d.detect("What is the difference between TCP and UDP protocols?")
    assert r2.detected is True


def test_normalize_strips_punctuation_for_dedup():
    d = _d()
    d.detect("What is your greatest weakness?")
    # Same words but no trailing "?" — should still be a dedup hit
    r2 = d.detect("What is your greatest weakness")
    assert r2.detected is False


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_rapid_second_trigger():
    d = _d(cooldown_seconds=10.0)
    d.detect("What is polymorphism in object-oriented programming exactly?")
    # Different question but within cooldown
    r2 = d.detect("How does inheritance work in Python programming language?")
    assert r2.detected is False


def test_cooldown_zero_allows_back_to_back():
    d = _d(cooldown_seconds=0.0)
    d.detect("What is polymorphism in object-oriented programming exactly?")
    r2 = d.detect("How does inheritance work in Python programming language?")
    assert r2.detected is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_string_no_crash():
    r = _d().detect("")
    assert r.detected is False
    assert r.kind == "none"


def test_whitespace_only_no_crash():
    r = _d().detect("   ")
    assert r.detected is False


def test_result_is_frozen_dataclass():
    r = _d().detect("What is polymorphism in Java programming language today?")
    with pytest.raises((AttributeError, TypeError)):
        r.detected = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# False-positive guards — WH words inside declarative statements
# ---------------------------------------------------------------------------

def test_wh_word_in_statement_not_detected():
    r = _d().detect("I know what you mean and I agree with you completely.")
    assert r.detected is False


def test_why_in_statement_not_detected():
    r = _d().detect("That is why I decided to leave the company last year.")
    assert r.detected is False


def test_how_in_statement_not_detected():
    r = _d().detect("I understand how the system works from reading the documentation.")
    assert r.detected is False


def test_kind_set_even_when_threshold_not_met():
    # WH at start scores 0.9; no trailing "?" so no boost — 0.9 < 0.95 threshold
    r = _d(confidence_threshold=0.95).detect("What is the time complexity of merge sort algorithm")
    assert r.detected is False
    assert r.kind == "question"
    assert r.confidence == pytest.approx(0.9)
