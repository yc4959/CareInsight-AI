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
    if tool["function"]["name"] == "ask_clarification":
        schema = tool["function"]["parameters"]
        schema["properties"]["options"] = {
            "type": "array", "items": {"type": "string"},
            "minItems": 2, "maxItems": 3,
        }
        schema["required"] = ["question", "options"]

SYSTEM = """
You help nontechnical users explore recorded depression screenings in
synthetic patient data. Use short, plain English. Never require users
to know database terms, denominator, prevalence, or coverage.
The page's selected year is 2020. Use it if no year is mentioned and
state it in the report. Never reinterpret an explicit different year
or a relative year as 2020. Ask which calendar year for relative dates.
Only one measure is supported: adult depression screening records.
Available breakdowns: everyone, age groups, and the recorded GENDER field.
No custom filters, diagnoses, symptom severity, or causal analysis.

If a question explicitly asks who has depression, explain that this
version cannot answer that. Do not substitute screening analysis.
If 'depression' or 'getting checked' is ambiguous, ask what they mean.
Use ask_clarification with ONE short question and 2-3 distinct plain
English answer options. Options may include unsupported requests;
explain limitations if the user chooses one. Do not steer every answer
into screening. Free-text answers must also be respected.
Only ask for missing information, never reconfirm an explicit screening
request. Interpret 'younger and older people' as age groups. If they ask
'who' without specifying a comparison, offer age groups or men and women.
For simple counts or rates without a breakdown, use overall.
Call get_screening_summary only when the intended measure is clear.
Use prior answers to resolve ambiguity. Do not repeatedly ask the same
question. Never silently drop a requested age filter or change a measure.

Reports: plain English, concise takeaway, counts and percentages to two
 decimals. Say 'people included' and 'people with a screening record'.
Explain the year and eligibility. Label F and M using their original
values and explain that these come from the dataset's GENDER field.
Use comparison.gap_percentage_points for gaps. Do not calculate new
statistics. Zero missing_group_count only means no missing values among
eligible people, not all possible categories being represented.
Missing screening records do not prove screening was not performed.
Do not infer actual coverage, causes, significance, or intervention effects.
Clearly label synthetic data. Do not show internal variable names.
Do not label gaps small, large, important, or meaningful: no such
threshold has been defined. State the numerical difference only.
Explain eligibility precisely: age 18+ on January 1, 2020; at least one
healthcare visit in 2020; no recorded death date or a death date after
December 31, 2020. Missing death dates mean no recorded death, not
verified survival. Describe this as the dataset inclusion rule.
Do not end with a question or offer a conversational follow-up:
the interface provides its own next-analysis instructions.
For clarification choices, say 'recorded depression diagnosis', not
'actually has depression'. A diagnosis record does not establish the
true prevalence of depression.
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
I help you explore recorded depression screenings in a synthetic patient dataset.

You can ask me to:
- Count people with or without a screening record.
- Compare screening records across age groups or the dataset's F/M categories.
- Show the percentage with a screening record and explain who was included.

Try: **Compare screening records between younger and older adults.**

I use **2020 data**. If your question is unclear, I will ask one simple
question before analyzing it. I cannot tell who has depression, explain
what caused a difference, recommend treatment, or analyze other years.
The data are synthetic, not real patient findings.

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
            "options": [
                "Recorded depression screenings (getting checked)",
                "Recorded depression diagnoses (not supported yet)",
            ],
        }
        state["clarifications"] += 1
        return

    reply = call_model(state["messages"], TOOLS)
    calls = reply.get("tool_calls") or []

    if not calls:
        state["notice"] = (
            "No data analysis was run. "
            "This version can compare recorded depression screenings in 2020. "
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
    if not isinstance(args, dict) or set(args) != {"year", "group_by"}:
        raise ValueError("Invalid arguments.")
    if type(args["year"]) is not int or args["year"] != 2020:
        raise ValueError("Unsupported year.")
    if not isinstance(args["group_by"], str):
        raise ValueError("Invalid grouping.")
    if args["group_by"] not in {"overall", "age_group", "gender"}:
        raise ValueError("Unsupported grouping.")

    result = get_screening_summary(**args)
    state["evidence"] = {"tool": name, "arguments": args, "result": result}
    state["messages"].append(reply)
    state["messages"].append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    })
    state["report"] = render_evidence_report(result)
    state["pending"] = None


def render_chat():
    st.divider()
    st.header("Ask CareInsight")
    st.caption(
        "Explore who has a recorded depression screening in this synthetic dataset. "
        "This version supports 2020 data only. "
        "The chart controls above do not filter this conversation."
    )
    st.markdown(
        "**Try:** Which age group has fewer recorded depression screenings?"
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
                if clarification.strip() == "Recorded depression diagnoses (not supported yet)":
                    state["notice"] = (
                        "This version cannot compare recorded depression diagnoses. "
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
