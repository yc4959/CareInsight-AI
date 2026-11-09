import json
import os
import re

import streamlit as st

from careinsight.agent import SYSTEM, TOOLS
from careinsight.agent_demo import call_model
from careinsight.summary_tool import get_screening_summary
from careinsight.reporting import render_evidence_report
from careinsight.help_intent import wants_product_help

# PLAIN_LANGUAGE_UI_V1: web policy; CLI benchmark v1 remains unchanged.
import copy
TOOLS = copy.deepcopy(TOOLS)
for tool in TOOLS:
    if tool["function"]["name"] == "get_screening_summary":
        tool["function"]["description"] = (
            "Calculate 2020 synthetic adult screening record coverage "
            "for depression or substance use; choose overall, age_group, or gender."
        )
        schema = tool["function"]["parameters"]
        schema["properties"]["metric"] = {
            "type": "string", "enum": ["depression", "substance_use", "both"]
        }
        schema["required"].append("metric")
    if tool["function"]["name"] == "ask_clarification":
        schema = tool["function"]["parameters"]
        schema["properties"]["options"] = {
            "type": "array", "items": {"type": "string"},
            "minItems": 2, "maxItems": 3,
        }
        schema["required"] = ["question", "options"]

SYSTEM = """
You help nontechnical users explore screening procedure records in
synthetic patient data. Always use short, plain English. The available
metrics are 2020 adult depression screening record coverage and 2020
adult substance use screening record coverage. The latter uses one code
whose source description is "Screening for drug abuse (procedure)".
These are records of getting checked, not diagnoses or proof that a
screening was actually performed. Both metrics share the same eligible
adult population. Available breakdowns: everyone, age groups, and the
original GENDER field. No custom filters or other years.

If the user names depression screening, use metric depression. If the
user names substance use or drug abuse screening, use substance_use.
If they ask only for "screening" without saying which kind, ask one
plain-language clarification with 2-3 options. If they say only
"depression" or only "substance use" without saying whether they mean
screening or diagnosis, ask which they mean. A request for diagnoses,
prevalence, severity, causes, treatment, or another measure is outside
scope. Explain that without running a screening analysis. If they ask
for both metrics in one question, use metric both to show two separate analyses. Do not ask which metric to run first.
Do not silently change a user's measure. Do not repeat a clarification
already answered. Free-text clarification answers must be respected.

Use 2020 if no year is mentioned; state the year in the result. Never
reinterpret another explicit year or a relative year as 2020. Ask for
the calendar year if a relative date is used. Interpret "younger and
older people" as age groups. If no breakdown is requested, use overall.
For a supported request, call get_screening_summary once with year,
group_by, and metric (depression, substance_use, or both). Use
ask_clarification for ambiguity, with one
short question and 2-3 distinct plain-English options.

Never invent numbers. The reporting code handles counts and prose from
validated tool evidence. Synthetic data cannot establish real-world
patterns, causes, significance, or intervention effects. Missing records
do not prove that screening did not happen. Preserve original F/M labels.
"""


def unsupported_year(text):
    years = set(re.findall(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", text))
    return bool(years - {"2020"})


# METRIC_GATE_V1: conservative guard for bare English "depression" requests.
def needs_metric_clarification(question):
    words = set(re.findall(r"[a-z]+", question.lower()))
    specific = {
        "screening", "screenings", "screened", "diagnosis", "diagnoses",
        "diagnosed", "prevalence", "severity", "symptoms",
    }
    # A population comparison alone does not identify what to measure.
    # Ask before selecting the screening metric.
    return not words.intersection(specific)


# CAPABILITIES_HELP_V1
CAPABILITIES_HELP = """
I help you explore recorded adult depression and substance use screenings
in a synthetic patient dataset.

You can ask how many people have a screening record, what percentage
that represents, or how the percentages compare by age group or the
dataset's F/M categories.

Try: **Compare substance use screening records across age groups.**

I use **2020 data**. If it is unclear which screening you mean, I will
ask a short question first. I cannot determine who has a diagnosis,
explain causes, recommend treatment, or analyze other years. These are
synthetic data, not real patient findings.

Select **Start a new analysis** to ask a data question.
"""


def is_capabilities_question(question):
    normalized = re.sub(r"[!?？。！,，.]+", "", question.lower()).strip()
    english = {
        "what can you do", "what can this ai do", "what can i ask",
        "how do i use this", "what does this app do", "help",
    }
    chinese = {"这ai能干啥", "这个ai能干什么", "你能干什么", "你能做什么",
               "这能干啥", "这个怎么用", "怎么用", "有什么功能"}
    return normalized in english or re.sub(r"\s+", "", normalized) in chinese


# TWO_METRICS_WEB_V1: offer plain-language choices for an unclear measure.
def metric_options(question):
    words = set(re.findall(r"[a-z]+", question.lower()))
    if "depression" in words and not {"substance", "drug"} & words:
        return [
            "Recorded depression screenings (getting checked)",
            "Recorded depression diagnoses (not supported)",
        ]
    if {"substance", "drug"} & words and "depression" not in words:
        return [
            "Recorded substance use screenings (getting checked)",
            "Recorded substance use diagnoses (not supported)",
        ]
    return [
        "Recorded depression screenings",
        "Recorded substance use screenings",
        "Both screening types, separately",
    ]


# BOTH_METRICS_WEB_V1: respect an explicit request for both measures.
def both_metrics_requested(state):
    question = state["question"].lower()
    has_depression = "depression" in question
    has_substance = "substance" in question or "drug" in question
    if any(term in question for term in (
        "diagnos", "prevalence", "severity", "treatment", "cause"
    )):
        return False
    if "screen" not in question:
        return False
    if has_depression and has_substance:
        return True
    if has_depression or has_substance:
        return False
    answers = [
        item.get("answer", "").strip().lower()
        for item in state.get("clarification_history", [])
    ]
    return any(answer in {
        "both", "both, separately", "both separately",
        "both screening types", "both screening types, separately",
    } for answer in answers)


def render_two_reports(results):
    if len(results) != 2:
        raise ValueError("Expected two metric results.")
    return (
        "**Two separate screening record measures** — each uses the same "
        "eligible adult population.\n\n"
        + "\n\n---\n\n".join(render_evidence_report(r) for r in results)
    )


def process_turn(state):
    if wants_product_help(state):
        state["help"] = CAPABILITIES_HELP
        state["notice"] = None
        state["pending"] = None
        return
    if (
        not state.get("clarification_history")
        and needs_metric_clarification(state["question"])
    ):
        state["pending"] = {
            "id": None,
            "question": "What would you like to compare?",
            "options": metric_options(state["question"]),
        }
        state["clarifications"] += 1
        return

    reply = call_model(state["messages"], TOOLS)
    calls = reply.get("tool_calls") or []

    if not calls:
        state["notice"] = (
            "No data analysis was run. "
            "This version can compare recorded depression or substance use "
            "screenings in 2020. "
            "Choose 'Start a new analysis' to ask another question."
        )
        state["pending"] = None
        return

    if len(calls) != 1:
        raise ValueError("Expected one tool call.")

    tool_call = calls[0]
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])

    if name == "ask_clarification":
        if (
            not isinstance(args, dict)
            or set(args) != {"question", "options"}
            or not isinstance(args["question"], str)
            or not args["question"].strip()
            or not isinstance(args["options"], list)
            or not 2 <= len(args["options"]) <= 3
            or not all(isinstance(x, str) and x.strip() for x in args["options"])
            or len(set(args["options"])) != len(args["options"])
        ):
            raise ValueError("Invalid clarification.")
        if state["clarifications"] >= 3:
            raise ValueError("Clarification limit reached.")
        state["messages"].append(reply)
        state["pending"] = {
            "id": tool_call["id"],
            "question": args["question"],
            "options": args["options"],
        }
        state["clarifications"] += 1
        return

    if name != "get_screening_summary":
        raise ValueError("Unsupported tool.")
    if not isinstance(args, dict) or set(args) != {"year", "group_by", "metric"}:
        raise ValueError("Invalid arguments.")
    if type(args["year"]) is not int or args["year"] != 2020:
        raise ValueError("Unsupported year.")
    if not isinstance(args["group_by"], str):
        raise ValueError("Invalid grouping.")
    if args["group_by"] not in {"overall", "age_group", "gender"}:
        raise ValueError("Unsupported grouping.")
    if args["metric"] not in {"depression", "substance_use", "both"}:
        raise ValueError("Unsupported metric.")

    metrics = (
        ("depression", "substance_use")
        if args["metric"] == "both" or both_metrics_requested(state)
        else (args["metric"],)
    )
    results = [
        get_screening_summary(year=args["year"], group_by=args["group_by"], metric=metric)
        for metric in metrics
    ]
    result = results[0] if len(results) == 1 else results
    state["evidence"] = {"tool": name, "arguments": args, "result": result}
    state["messages"].append(reply)
    state["messages"].append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    })
    state["report"] = (
        render_evidence_report(result) if len(results) == 1
        else render_two_reports(results)
    )
    state["pending"] = None


def render_chat():
    st.divider()
    st.header("Ask CareInsight")
    st.caption(
        "Explore recorded depression or substance use screenings in this "
        "synthetic dataset. "
        "This version supports 2020 data only. "
        "The chart controls above do not filter this conversation."
    )
    st.markdown(
        "**Try:** Which age group has fewer recorded substance use screenings?"
    )

    with st.expander("What can I ask?"):
        st.markdown(CAPABILITIES_HELP)

    if not os.getenv("DEEPSEEK_API_KEY"):
        st.warning("API key is not configured in this server session.")
        return

    if "careinsight_chat" not in st.session_state:
        st.session_state.careinsight_chat = None

    if st.button("Start a new analysis"):
        st.session_state.careinsight_chat = None
        st.rerun()

    state = st.session_state.careinsight_chat
    # REPORT_CONTEXT_V1: keep an explicit record of user clarifications.
    if state is not None:
        state.setdefault("clarification_history", [])
    submitted = False

    if state is None:
        with st.form("new_analysis", clear_on_submit=True):
            question = st.text_area("Your question", height=100)
            submitted = st.form_submit_button("Analyze")

        if submitted:
            if not question.strip():
                st.warning("Please enter a question.")
                return
            if unsupported_year(question):
                st.warning("Only 2020 is currently supported.")
                return

            state = {
                "question": question.strip(),
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM + (
                            "\nUse comparison.gap_percentage_points for gaps. "
                            "Make missingness claims only when "
                            "missing_group_count is explicitly provided."
                        ),
                    },
                    {"role": "user", "content": question.strip()},
                ],
                "pending": None,
                "clarifications": 0,
                "clarification_history": [],
                "report": None,
                "evidence": None,
                "notice": None,
            }
            st.session_state.careinsight_chat = state

    elif state["pending"]:
        st.write("**Original question:**", state["question"])
        st.info(state["pending"]["question"])
        with st.form("clarification", clear_on_submit=True):
            selected = st.radio(
                "Choose an answer",
                state["pending"].get("options", []),
                index=None,
            )
            written = st.text_input("Or answer in your own words")
            submitted = st.form_submit_button("Continue")
            clarification = written.strip() or selected or ""

        if submitted:
            if not clarification.strip():
                st.warning("Please answer the clarification.")
                return
            if unsupported_year(clarification):
                state["notice"] = "Analysis stopped: only 2020 is supported."
                state["pending"] = None
                st.rerun()

            state["clarification_history"].append({
                "question": state["pending"]["question"],
                "answer": clarification.strip(),
            })
            if state["pending"]["id"] is None:
                state["messages"].append({
                    "role": "assistant",
                    "content": state["pending"]["question"] + " Options: "
                    + "; ".join(state["pending"]["options"]),
                })
                state["messages"].append({
                    "role": "user",
                    "content": clarification.strip(),
                })
                if clarification.strip() in {
                    "Recorded depression diagnoses (not supported)",
                    "Recorded substance use diagnoses (not supported)",
                    "Diagnoses (not supported)",
                }:
                    state["notice"] = (
                        "This version cannot compare diagnoses. "
                        "No screening analysis was run."
                    )
                    state["pending"] = None
                    st.rerun()
            else:
                state["messages"].append({
                    "role": "tool",
                    "tool_call_id": state["pending"]["id"],
                    "content": json.dumps({"user_answer": clarification.strip()}),
                })
            state["pending"] = None

    if submitted:
        try:
            with st.spinner("Interpreting your question and checking evidence..."):
                process_turn(state)
        except Exception:
            state["pending"] = None
            state["notice"] = (
                "The analysis could not be completed. No automatic retry "
                "was made. Start a new analysis to try again."
            )
        st.rerun()

    if state:
        if not state["pending"]:
            st.subheader("Your request")
            st.write(state["question"])
            for item in state.get("clarification_history", []):
                st.write("**We asked:**", item["question"])
                st.write("**You answered:**", item["answer"])
        if state.get("help"):
            st.subheader("What CareInsight can do")
            st.markdown(state["help"])
        if state["notice"]:
            st.warning(state["notice"])

        if state["report"]:
            st.subheader("What we found")
            st.caption("Calculated results · Report generated directly from analysis evidence.")
            st.markdown(state["report"])
            st.caption(
                "To explore another comparison, select 'Start a new analysis'."
            )

        if state["evidence"]:
            with st.expander("How this was calculated"):
                st.json(state["evidence"])

        if not state["pending"] and not state["report"]:
            st.caption("Use 'Start a new analysis' to submit another question.")
