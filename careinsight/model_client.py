"""Model API client shared by the current CareInsight analysis flow."""

import json
import os
import urllib.error
import urllib.request


def call_model(messages, tools=None):
    """Request one model turn; return its message and never expose the API key."""
    payload = {
        "model": os.environ["DEEPSEEK_MODEL"],
        "messages": messages,
        "thinking": {"type": "disabled"},
        "max_tokens": 800,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    request = urllib.request.Request(
        os.environ["DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"].strip(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    usage = result.get("usage", {})
    print("Tokens used in this model call:", usage.get("total_tokens"))
    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("The model response was truncated; no analysis was published.")
    return choice["message"]
