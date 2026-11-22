"""Unit tests for chat guardrails: validation and intent classification."""

import pytest

from app.services.guardrails import (
    CAPABILITY_ANSWER,
    GREETING_ANSWER,
    MAX_MESSAGE_LENGTH,
    MessageValidationError,
    OFF_TOPIC_ANSWER,
    classify_message,
    validate_message,
)


class TestValidateMessage:
    def test_accepts_normal_message(self):
        assert validate_message("Who has Python experience?") == (
            "Who has Python experience?"
        )

    def test_rejects_empty_message(self):
        with pytest.raises(MessageValidationError):
            validate_message("   ")

    def test_rejects_none_message(self):
        with pytest.raises(MessageValidationError):
            validate_message(None)

    def test_rejects_oversized_message(self):
        with pytest.raises(MessageValidationError):
            validate_message("a" * (MAX_MESSAGE_LENGTH + 1))

    def test_accepts_message_at_limit(self):
        assert validate_message("a" * MAX_MESSAGE_LENGTH) == "a" * MAX_MESSAGE_LENGTH

    def test_rejects_control_character_flood(self):
        message = "question " + ("\x00" * 25) + " more"
        with pytest.raises(MessageValidationError):
            validate_message(message)

    def test_strips_surrounding_whitespace(self):
        assert validate_message("  hello  ") == "hello"


class TestClassifyMessage:
    def test_greetings_are_recognized(self):
        for text in ("hi", "Hello!", "Hey there", "Good morning", "Thank you"):
            assert classify_message(text) == "greeting"

    def test_capability_questions_are_recognized(self):
        for text in (
            "What can you do?",
            "Who are you?",
            "What are your capabilities?",
            "How can you help me?",
            "What can I ask you?",
        ):
            assert classify_message(text) == "capability"

    def test_recruitment_questions_are_recognized(self):
        for text in (
            "Who has Python experience?",
            "Summarize the resume of Priya Sharma",
            "What are the requirements for the backend job?",
            "Which candidates match the AI Engineer role?",
            "List my uploaded documents",
            "Explain the skills missing in Arjun's profile",
        ):
            assert classify_message(text) == "recruitment"

    def test_clearly_unrelated_questions_are_rejected(self):
        for text in (
            "What's the weather today?",
            "Who won the cricket match yesterday?",
            "Tell me a joke",
            "What is the capital of France?",
            "Give me a recipe for pasta",
            "What is the price of bitcoin?",
            "Book me a flight to Paris",
        ):
            assert classify_message(text) == "off_topic"

    def test_recruitment_beats_generic_patterns(self):
        assert classify_message("Which candidates match this job?") == "recruitment"

    def test_unknown_questions_fall_through_to_general(self):
        assert classify_message("Tell me about Priya") == "general"

    def test_empty_message_is_general(self):
        assert classify_message("") == "general"

    def test_fixed_answers_are_non_empty_strings(self):
        assert GREETING_ANSWER
        assert CAPABILITY_ANSWER
        assert OFF_TOPIC_ANSWER
