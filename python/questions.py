#!/usr/bin/env python3
"""Validation helpers for structured questions returned by chat models."""

import json


QUESTION_MARKER = "#Question"


def question_payload(content):
    """Return a validated question payload, or None for a normal response."""
    try:
        payload = json.loads(content.strip())
    except (TypeError, json.JSONDecodeError):
        return None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("questions"), list)
            or not payload["questions"]):
        return None
    for question in payload["questions"]:
        if not isinstance(question, dict) or not isinstance(question.get("question"), str):
            return None
        if not isinstance(question.get("header", ""), str):
            return None
        if not isinstance(question.get("options"), list) or not question["options"]:
            return None
        for option in question["options"]:
            if not isinstance(option, dict) or not isinstance(option.get("label"), str):
                return None
            if not isinstance(option.get("description", ""), str):
                return None
            if "user_prompt" in option and not isinstance(option["user_prompt"], bool):
                return None
    return payload
