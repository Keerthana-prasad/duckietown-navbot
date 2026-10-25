"""LLM Client for Cloud API Integration (Gemini, OpenAI) with Heuristic Mock Fallback.

Supports:
- Google Gemini API (v1beta generateContent)
- OpenAI API (v1 chat/completions)
- High-fidelity heuristic parser fallback when offline or API key is unset
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for querying cloud LLM models to parse navigation intents."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("llm", {})
        self.provider = self.config.get("provider", "gemini").lower()
        self.model = self.config.get("model", "gemini-1.5-flash")
        self.timeout = float(self.config.get("timeout_seconds", 10.0))
        self.temperature = float(self.config.get("temperature", 0.1))
        self.fallback_to_heuristic = bool(self.config.get("fallback_to_heuristic", True))

        # Retrieve API key securely from environment variable
        env_var_name = self.config.get("api_key_env_var", "GEMINI_API_KEY")
        self.api_key = os.getenv(env_var_name) or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.warning(
                f"No API key found in environment variable '{env_var_name}' or 'GEMINI_API_KEY'. "
                f"Running in heuristic mock mode."
            )

    def is_cloud_ready(self) -> bool:
        """Returns True if provider and API key are configured for cloud queries."""
        return bool(self.api_key and self.provider in ("gemini", "openai"))

    def query(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Query LLM with system prompt and user instructions.

        Falls back gracefully if network fails, timeout occurs, or no API key is set.
        """
        if not self.is_cloud_ready():
            logger.info("Using heuristic/mock LLM parser (no cloud API key configured).")
            return self._heuristic_parse(user_prompt)

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_prompt)
            elif self.provider == "openai":
                return self._call_openai(system_prompt, user_prompt)
            else:
                logger.warning(f"Unknown provider '{self.provider}', falling back to heuristic parser.")
                return self._heuristic_parse(user_prompt)
        except Exception as e:
            logger.error(f"Cloud LLM API error ({type(e).__name__}): {e}")
            if self.fallback_to_heuristic:
                logger.info("Falling back to local heuristic intent parser.")
                return self._heuristic_parse(user_prompt)
            raise

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Call Google Gemini generateContent API via REST."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nUser instruction:\n{user_prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }

        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        text_content = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return self._extract_json(text_content)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Call OpenAI chat/completions API via REST."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model if "gpt" in self.model else "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return self._extract_json(content)

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from LLM response text."""
        cleaned = raw_text.strip()
        # Remove markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)

        # Find first '{' and last '}'
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]

        return json.loads(cleaned)

    def _heuristic_parse(self, user_prompt: str) -> Dict[str, Any]:
        """Deterministic, rule-based parser used for offline testing, mocking, and fallback."""
        query = user_prompt.strip().lower()

        # 1. Stop / Halt intent
        if any(w in query for w in ["stop", "halt", "freeze", "abort", "stand still", "brake"]):
            return {
                "intent": "stop",
                "target": None,
                "target_attributes": {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 0.0, "stop_at_target": True},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 1.0,
            }

        # 2. Unsupported actions
        unsupported_verbs = ["fly", "jump", "cook", "clean", "dance", "speak", "climb", "pour", "drink"]
        if any(v in query for v in unsupported_verbs):
            return {
                "intent": "unsupported",
                "target": None,
                "target_attributes": {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 1.0, "stop_at_target": True},
                "requires_clarification": True,
                "clarification_message": (
                    "Duckiebot DB21J is a ground vehicle equipped with a camera and differential motors. "
                    "It cannot perform physical manipulation, flight, or non-ground actions."
                ),
                "confidence": 0.0,
            }

        # 3. Known landmarks
        landmark_map = {
            "laboratory": ["laboratory", "lab", "science lab", "station a"],
            "entrance": ["entrance", "door", "gate", "entry", "front entrance"],
            "pickup_point": ["pickup point", "pickup", "dock", "loading dock", "station b"],
            "charging_station": ["charging station", "charger", "power station", "docking station"],
            "duckie_crossing": ["duckie crossing", "duckies", "crossing", "pedestrian area"],
        }

        matched_landmark = None
        for landmark_key, aliases in landmark_map.items():
            if any(alias in query for alias in aliases):
                matched_landmark = landmark_key
                break

        # Check for color / object queries
        colors = ["red", "blue", "green", "yellow", "white", "black", "orange", "purple"]
        objects = ["object", "bottle", "cup", "box", "duckie", "traffic light", "marker", "obstacle", "can"]

        matched_color = next((c for c in colors if c in query), None)
        matched_obj = next((o for o in objects if o in query), None)

        is_search_query = any(w in query for w in ["find", "search", "look for", "locate", "spot"])

        if is_search_query and (matched_obj or matched_color):
            target_str = f"{matched_color + ' ' if matched_color else ''}{matched_obj if matched_obj else 'object'}"
            return {
                "intent": "search_for_object",
                "target": target_str,
                "target_attributes": {"color": matched_color, "reference_landmark": matched_landmark} if matched_color else {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 0.85, "stop_at_target": True},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 0.95,
            }

        if matched_landmark:
            return {
                "intent": "navigate_to_landmark",
                "target": matched_landmark,
                "target_attributes": {"color": matched_color} if matched_color else {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 1.0, "stop_at_target": True},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 0.95,
            }

        if matched_obj or matched_color:
            target_str = f"{matched_color + ' ' if matched_color else ''}{matched_obj if matched_obj else 'object'}"
            return {
                "intent": "search_for_object",
                "target": target_str,
                "target_attributes": {"color": matched_color} if matched_color else {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 0.85, "stop_at_target": True},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 0.90,
            }

        if any(w in query for w in ["lane", "follow", "track", "stay in lane"]):
            return {
                "intent": "follow_lane",
                "target": "lane",
                "target_attributes": {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 1.0, "stop_at_target": False},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 0.92,
            }

        if any(w in query for w in ["explore", "wander", "patrol", "look around"]):
            return {
                "intent": "explore",
                "target": "duckietown",
                "target_attributes": {},
                "constraints": {"avoid_obstacles": True, "max_speed_ratio": 0.75, "stop_at_target": False},
                "requires_clarification": False,
                "clarification_message": None,
                "confidence": 0.85,
            }

        # Ambiguous / underspecified
        return {
            "intent": "ambiguous",
            "target": None,
            "target_attributes": {},
            "constraints": {"avoid_obstacles": True, "max_speed_ratio": 1.0, "stop_at_target": True},
            "requires_clarification": True,
            "clarification_message": (
                "Destination is unclear. Please specify a recognized landmark (laboratory, entrance, pickup point, charging station) "
                "or visual target (e.g., 'find the red object', 'go to the lab', 'follow the lane')."
            ),
            "confidence": 0.25,
        }
