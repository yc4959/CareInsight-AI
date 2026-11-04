import json
import re
import urllib.error

from careinsight.agent_demo import call_model
from careinsight.summary_tool import get_screening_summary


TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_screening_summary",
        "description": (
            "Calculate 2020 depression screening record coverage from "
            "Synthea data. Choose overall, age_group, or gender. "
            "No custom population filters or year comparisons are supported."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "enum": [2020]},
                "group_by": {
                    "type": "string",
                    "enum": ["overall", "age_group", "gender"],
                },
            },
            "required": ["year", "group_by"],
            "additionalProperties": False,
        },
    },
}]

TOOLS.append({
    "type": "function",
    "function": {
        "name": "ask_clarification",
        "description": (
            "Ask the user to clarify an ambiguous metric or request "
            "before running any analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"}
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
})

SYSTEM = '\nYou are CareInsight, a synthetic population health analytics assistant.\nAlways respond in English.\n\nSupported analysis:\n2020 adult depression screening record coverage, overall or grouped\nby age_group or the original GENDER field. No custom filters.\n\nDecision rules:\n1. If the user explicitly mentions depression screening or screening\n   records, the metric is clear. Do not ask them to confirm it again.\n   Questions about counts, missing records, rates, denominators,\n   rankings, or gaps are supported.\n2. When no grouping is requested, use overall. Do not ask the user\n   to choose a grouping unnecessarily.\n3. If the user says only "depression" without identifying a measure,\n   ask which measure they mean using ask_clarification.\n4. Explicit diagnoses, prevalence, severity, other screening measures,\n   unsupported years, or custom filters are outside scope.\n   Explain the limitation in plain text and do not call either tool.\n   You may mention supported alternatives without asking a follow-up.\n5. If the year is absent, use ask_clarification to ask whether the\n   user wants the supported year 2020.\n   For relative years such as "last year", ask for the calendar year\n   and explain that only 2020 is supported. Never equate last year\n   with 2020.\n6. Ask only for information that is actually missing or ambiguous.\n   Use the user\'s clarification; do not repeat answered questions.\n7. For a supported request, call get_screening_summary once with\n   the correct year and grouping.\n\nReporting rules:\nUse only returned evidence. Report numerator, denominator, year,\nand coverage percentages to two decimal places.\nUse comparison.gap_percentage_points for group gaps.\nExplain the denominator and synthetic-data limitations.\nPreserve original GENDER labels.\nZero missing_group_count means no missing grouping values among\neligible patients, not that every possible category is represented.\nMissing documentation does not establish whether screening occurred.\nDo not infer actual coverage, causes, significance, or intervention effects.\nUse readable metric names, not internal identifiers.\n'


def main():
    question = input("Enter your analysis question: ").strip()
    if not question:
        print("No question entered.")
        return

    years = set(re.findall(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", question))
    if years - {"2020"}:
        print("Analysis not run: only 2020 is currently supported.")
        return

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    for attempt in range(3):
        reply = call_model(messages, TOOLS)
        calls = reply.get("tool_calls") or []

        if len(calls) != 1:
            break

        clarification = calls[0]
        if clarification["function"]["name"] != "ask_clarification":
            break

        args = json.loads(clarification["function"]["arguments"])
        if (
            not isinstance(args, dict)
            or set(args) != {"question"}
            or not isinstance(args["question"], str)
            or not args["question"].strip()
        ):
            raise ValueError("Invalid clarification request.")

        print("\\nClarification:", args["question"])
        user_answer = input("Your answer: ").strip()
        if not user_answer:
            print("Analysis not run: clarification was not provided.")
            return

        answer_years = set(re.findall(
            r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", user_answer
        ))
        if answer_years - {"2020"}:
            print("Analysis not run: only 2020 is supported.")
            return

        messages.append(reply)
        messages.append({
            "role": "tool",
            "tool_call_id": clarification["id"],
            "content": json.dumps({"user_answer": user_answer}),
        })
    else:
        print("Clarification limit reached. Please restate your question.")
        return

    if not calls:
        print("Model response (no analysis executed):")
        print(reply.get("content") or "[No text response]")
        print(
            "No analysis was run. Supported scope: 2020 depression "
            "screening coverage, overall or grouped by age or GENDER. "
            "Please specify a supported analysis."
        )
        return
    if len(calls) != 1:
        raise ValueError("Expected one tool call.")

    tool_call = calls[0]
    function = tool_call["function"]
    if function["name"] != "get_screening_summary":
        raise ValueError("Unsupported tool.")

    args = json.loads(function["arguments"])
    if not isinstance(args, dict) or set(args) != {"year", "group_by"}:
        raise ValueError("Invalid tool arguments.")
    if type(args["year"]) is not int or args["year"] != 2020:
        raise ValueError("Unsupported year.")
    if not isinstance(args["group_by"], str):
        raise ValueError("Invalid grouping.")
    if args["group_by"] not in {"overall", "age_group", "gender"}:
        raise ValueError("Unsupported grouping.")

    print("Selected tool:", function["name"])
    print("Tool arguments:", args)
    result = get_screening_summary(**args)
    print("Local tool result:", json.dumps(result, ensure_ascii=False))

    messages.append(reply)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    })
    answer = call_model(messages)
    if not answer.get("content"):
        raise ValueError("No report was returned.")
    print("\n=== AI Analysis Report (Review Required) ===")
    print(answer["content"])


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print("API request failed. HTTP status:", error.code)
    except urllib.error.URLError:
        print("Network connection failed.")
    except TimeoutError:
        print("Request timed out.")
    except (ValueError, RuntimeError) as error:
        print("Analysis stopped:", error)
