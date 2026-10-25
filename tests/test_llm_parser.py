"""Unit tests for LLM Destination Interpreter and Intent Parser."""

import pytest
from llm.schemas import NavigationIntent, InterpretedGoal
from llm.intent_parser import IntentParser

# Sample test configuration with known landmarks
TEST_CONFIG = {
    "llm": {
        "provider": "mock",
        "fallback_to_heuristic": True
    },
    "computer_vision": {
        "landmarks": {
            "laboratory": {
                "aliases": ["lab", "science lab"],
                "visual_indicator": "bottle"
            },
            "entrance": {
                "aliases": ["door", "entry"],
                "visual_indicator": "box"
            },
            "pickup_point": {
                "aliases": ["dock", "station b"],
                "visual_indicator": "cup"
            }
        }
    }
}


@pytest.fixture
def parser():
    return IntentParser(TEST_CONFIG)


def test_parse_valid_landmark_destination(parser):
    """Test standard landmark destination: 'Go to the laboratory'."""
    goal = parser.parse("Go to the laboratory")
    assert goal.intent == NavigationIntent.NAVIGATE_TO_LANDMARK
    assert goal.target == "laboratory"
    assert goal.mapped_landmark == "laboratory"
    assert goal.visual_indicator == "bottle"
    assert not goal.requires_clarification
    assert goal.constraints.avoid_obstacles is True


def test_parse_search_for_object(parser):
    """Test object search: 'Find the red object near the entrance'."""
    goal = parser.parse("Find the red object near the entrance")
    assert goal.intent == NavigationIntent.SEARCH_FOR_OBJECT
    assert "red" in goal.target
    assert not goal.requires_clarification
    assert goal.constraints.avoid_obstacles is True


def test_parse_stop_command(parser):
    """Test robot halt command: 'Stop when you reach the target'."""
    goal = parser.parse("Stop when you reach the target")
    assert goal.intent == NavigationIntent.STOP
    assert not goal.requires_clarification
    assert goal.constraints.max_speed_ratio == 0.0


def test_parse_ambiguous_destination(parser):
    """Test ambiguous instructions: 'Go somewhere quickly'."""
    goal = parser.parse("Go somewhere quickly")
    assert goal.requires_clarification is True
    assert goal.clarification_message is not None
    assert "clarification" in goal.clarification_message.lower() or "unclear" in goal.clarification_message.lower()


def test_parse_unsupported_task(parser):
    """Test unsupported actions: 'Fly to the roof'."""
    goal = parser.parse("Fly to the roof")
    assert goal.intent == NavigationIntent.UNSUPPORTED
    assert goal.requires_clarification is True
    assert "cannot fly" in goal.clarification_message.lower() or "ground" in goal.clarification_message.lower()


def test_parse_empty_query(parser):
    """Test handling of empty or whitespace-only queries."""
    goal = parser.parse("   ")
    assert goal.requires_clarification is True
    assert goal.target is None
