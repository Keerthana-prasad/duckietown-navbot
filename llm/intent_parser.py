"""LLM Intent Parser: Coordinates cloud/heuristic LLM and verifies destination schema."""

import logging
from typing import Dict, Any, Tuple
from pydantic import ValidationError

from llm.schemas import InterpretedGoal, NavigationIntent, Constraints
from llm.client import LLMClient
from llm.prompts import SYSTEM_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class IntentParser:
    """Parses natural-language user requests into validated navigation goals."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.landmarks_config = config.get("computer_vision", {}).get("landmarks", {})
        self.client = LLMClient(config)
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Dynamically assemble the system prompt with active landmarks."""
        names = list(self.landmarks_config.keys())
        landmarks_list = ", ".join(names)
        
        desc_lines = []
        for name, details in self.landmarks_config.items():
            aliases = ", ".join(details.get("aliases", []))
            vis = details.get("visual_indicator", "generic")
            desc_lines.append(f"- {name}: visual target '{vis}', aliases: [{aliases}]")
        landmarks_desc = "\n".join(desc_lines)

        return SYSTEM_PROMPT_TEMPLATE.format(
            landmarks_list=landmarks_list,
            landmarks_description=landmarks_desc
        )

    def parse(self, user_text: str) -> InterpretedGoal:
        """Parse natural-language query into a validated InterpretedGoal."""
        if not user_text or not user_text.strip():
            return InterpretedGoal(
                intent=NavigationIntent.AMBIGUOUS,
                target=None,
                requires_clarification=True,
                clarification_message="Empty request received. Please provide a destination or action.",
                confidence=0.0,
                raw_query="",
            )

        raw_query = user_text.strip()
        logger.info(f"Interpreting natural-language request: '{raw_query}'")

        try:
            raw_response = self.client.query(self.system_prompt, raw_query)
            goal = self._validate_and_enrich(raw_response, raw_query)
            return goal
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return InterpretedGoal(
                intent=NavigationIntent.AMBIGUOUS,
                target=None,
                requires_clarification=True,
                clarification_message=f"Could not parse navigation instruction: {str(e)}",
                confidence=0.0,
                raw_query=raw_query,
            )

    def _validate_and_enrich(self, raw_data: Dict[str, Any], raw_query: str) -> InterpretedGoal:
        """Validate raw dictionary against Pydantic schema and enrich with landmark mapping."""
        # Ensure raw_query is set
        raw_data["raw_query"] = raw_query

        # Map string intent safely to enum
        intent_str = str(raw_data.get("intent", "ambiguous")).lower()
        try:
            intent_enum = NavigationIntent(intent_str)
        except ValueError:
            intent_enum = NavigationIntent.AMBIGUOUS

        raw_data["intent"] = intent_enum

        # Ensure constraints dict has safe defaults
        constraints_raw = raw_data.get("constraints", {})
        if not isinstance(constraints_raw, dict):
            constraints_raw = {}
        # Safety guarantee: avoid_obstacles CANNOT be disabled by user LLM prompt
        constraints_raw["avoid_obstacles"] = True
        raw_data["constraints"] = Constraints(**constraints_raw)

        # Validate with Pydantic
        goal = InterpretedGoal(**raw_data)

        # Enrich landmark mapping if applicable
        if goal.intent == NavigationIntent.NAVIGATE_TO_LANDMARK and goal.target:
            target_norm = goal.target.strip().lower()
            mapped, indicator = self._resolve_landmark(target_norm)
            goal.mapped_landmark = mapped
            goal.visual_indicator = indicator
            if not mapped:
                # Landmark not found in verified database
                goal.requires_clarification = True
                valid_names = ", ".join(self.landmarks_config.keys())
                goal.clarification_message = (
                    f"Landmark '{goal.target}' is not in the robot's verified map database. "
                    f"Known landmarks are: {valid_names}."
                )

        elif goal.intent == NavigationIntent.SEARCH_FOR_OBJECT and goal.target:
            # Associate visual indicator directly with the target
            goal.visual_indicator = goal.target.lower()

        logger.info(
            f"Successfully interpreted: intent={goal.intent.value}, target={goal.target}, "
            f"indicator={goal.visual_indicator}, clarification={goal.requires_clarification}"
        )
        return goal

    def _resolve_landmark(self, target_str: str) -> Tuple[str, str]:
        """Find matching landmark from configuration aliases."""
        for name, details in self.landmarks_config.items():
            if target_str == name.lower():
                return name, details.get("visual_indicator", name)
            for alias in details.get("aliases", []):
                if alias.lower() in target_str or target_str in alias.lower():
                    return name, details.get("visual_indicator", name)
        return "", ""
