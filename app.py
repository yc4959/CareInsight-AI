"""One CareInsight UI for independently checked and exploratory analyses."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from careinsight.open_analysis import analyze
from careinsight.followup_context import context_from_result
from careinsight.charts import chart_options, is_time_column, make_chart

EXAMPLE_QUESTIONS = (
    "Compare adult substance use screening record coverage by GENDER in 2020.",
    "How many adults had a depression screening record in 2018?",
    "How did adult depression screening record coverage change between 2019 and 2020?",
    "Which procedure descriptions appeared most often in 2020? Show the top 10 by number of records.",
    "Which encounter types have the most substance use screening procedure records in 2020?",
    "Show procedure record counts by encounter type and year from 2018 to 2020.",
)


def select_example(question: str) -> None:
    """Fill the question box and start a fresh conversation without calling the model."""
    st.session_state.explore_question_input = question
    st.session_state.explore_result = None
    st.session_state.explore_error = None
    st.session_state.explore_history = []
    st.session_state.explore_followup_context = []
    st.session_state.explore_followup_mode = False


st.set_page_config(page_title="CareInsight AI", page_icon="📊", layout="wide")
st.title("CareInsight AI")
st.caption("Synthetic Synthea data · One analysis workflow · Visible evidence levels")
st.info(
    "Ask a descriptive question about patients, encounters, or procedure records. "
    "The agent selects a verified screening measure, read-only SQL, or a "
    "parameterized Pandas analysis. Choose a chart type when the returned "
    "aggregate data supports it."
)
st.warning(
    "Verified screening results match an independently calculated reference "
    "for defined 2018, 2019, and 2020 annual measures. The 2021 sample stops in "
    "November and is not used for full-year comparisons. Other questions "
    "remain exploratory: query "
    "restrictions and result checks cannot verify every new question's meaning."
)

with st.expander("What works now · Full product vision · Free hosting limits"):
    st.markdown(
        "**Available now**\n\n"
        "The hosted app contains **all rows** from four Synthea tables: patients, "
        "encounters, procedures, and conditions. Only approved analysis columns are "
        "packaged. You can ask descriptive aggregate questions about these records. "
        "The two custom adult screening-record measures are independently checked "
        "for full calendar years 2018, 2019, and 2020. The reviewed cross-year "
        "comparison currently covers 2019 and 2020. Other years and questions "
        "may be explored as records, but "
        "they do not inherit that verified-measure label. The sample ends in "
        "November 2021.\n\n"
        "**Full product vision**\n\n"
        "Add useful fields and tables from the larger Synthea download, then "
        "define and independently check each new cohort, measure, time window, "
        "and chart before calling its result verified. Expand the agent's tool "
        "choices and evaluation as the supported analyses grow. These are planned "
        "capabilities, not features of this live demo.\n\n"
        "**Why the whole download is not hosted here**\n\n"
        "The local source download has 18 CSV files and is about 539 MB "
        "uncompressed; its largest CSV is about 296 MB. GitHub blocks ordinary "
        "repository files above 100 MB, and Streamlit Community Cloud has "
        "limited memory and may put inactive apps to sleep. Uploading files "
        "alone would not make the agent understand or verify new measures. "
        "See the [annual data audit](https://github.com/yc4959/CareInsight-AI/blob/main/docs/annual_data_audit.md), "
        "[scope and roadmap](https://github.com/yc4959/CareInsight-AI/blob/main/docs/scope_and_roadmap.md), "
        "[GitHub limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits), "
        "and [Streamlit resource limits](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)."
    )

st.caption(
    "New here? The first example is ready to analyze. Select another example to fill "
    "the question box, or write your own. The first visit may take a moment to start."
)
with st.expander("Example questions", expanded=True):
    for index, example in enumerate(EXAMPLE_QUESTIONS, start=1):
        st.button(
            example,
            key=f"example_question_{index}",
            on_click=select_example,
            args=(example,),
        )
    st.caption(
        "These are starting points. You can edit the question or ask your own descriptive question. "
        "Recorded procedures do not establish diagnoses or completed screening."
    )

with st.expander("Evaluation: what has been checked"):
    st.markdown(
        "**30-question fixed evaluation:** 27/30 on the original live run and "
        "29/30 after correcting two overly literal response-phrase checks using "
        "the saved outputs. The remaining failure was an ambiguous question for "
        "which the model proposed a tool before the request check rejected it. "
        "That wording was subsequently fixed in local tests; the 30-question live "
        "run has not yet been repeated. These results are not a general accuracy "
        "or routing estimate. "
        "Earlier failures and evaluator corrections are documented in "
        "[the evaluation report](https://github.com/yc4959/CareInsight-AI/blob/main/evaluation/report.md)."
    )

if not all(os.getenv(key) for key in (
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
)):
    st.error("The model connection is not configured in this server session.")
    st.stop()

if "explore_history" not in st.session_state:
    st.session_state.explore_history = []
if "explore_followup_context" not in st.session_state:
    st.session_state.explore_followup_context = []
if "explore_followup_mode" not in st.session_state:
    st.session_state.explore_followup_mode = False
if "explore_question_input" not in st.session_state:
    st.session_state.explore_question_input = EXAMPLE_QUESTIONS[0]

if st.button("Start a new question"):
    st.session_state.explore_result = None
    st.session_state.explore_error = None
    st.session_state.explore_history = []
    st.session_state.explore_followup_context = []
    st.session_state.explore_followup_mode = False
    st.session_state.explore_question_input = EXAMPLE_QUESTIONS[0]
    st.rerun()

previous = st.session_state.get("explore_result")
pending = (previous is not None and previous["status"] == "no_analysis"
           and len(st.session_state.explore_history) < 4)
followup_mode = st.session_state.explore_followup_mode and not pending
if pending:
    st.write("**Original question:**", previous["question"])
    st.info(previous["message"])
    with st.form("explore_clarification"):
        question = st.text_input("Your answer")
        submitted = st.form_submit_button("Continue")
elif followup_mode:
    st.caption("Your next question will use the completed analysis below as context. "
               "The agent will run a fresh analysis for any new result.")
    with st.form("explore_followup"):
        question = st.text_input("Follow-up question",
                                 placeholder="Break that down by age group.")
        submitted = st.form_submit_button("Analyze follow-up")
else:
    with st.form("explore_question"):
        question = st.text_input(
            "Your analysis question",
            placeholder="Which procedure descriptions appeared most often in 2020?",
            key="explore_question_input",
        )
        submitted = st.form_submit_button("Analyze")

if submitted:
    history = (st.session_state.explore_history.copy() if pending else
               st.session_state.explore_followup_context.copy() if followup_mode else [])
    if pending:
        history.extend([
            {"role": "user", "content": previous["question"]},
            {"role": "assistant", "content": previous["message"]},
        ])
    st.session_state.explore_result = None
    st.session_state.explore_error = None
    if not question.strip():
        st.session_state.explore_error = (
            "Answer the clarification." if pending else "Enter a question before analyzing."
        )
        if pending:
            st.session_state.explore_result = previous
    else:
        try:
            with st.spinner("Choosing a tool, running the analysis, and checking the result..."):
                st.session_state.explore_result = analyze(question.strip(), history=history)
            st.session_state.explore_history = history
            new_result = st.session_state.explore_result
            if new_result["status"] in {"validated", "exploratory"}:
                st.session_state.explore_followup_context = context_from_result(new_result)
            st.session_state.explore_followup_mode = False
        except (ValueError, RuntimeError) as exc:
            st.session_state.explore_error = str(exc)
        except Exception:
            st.session_state.explore_error = (
                "The analysis could not be completed. No result was published."
            )
    st.rerun()

if st.session_state.get("explore_error"):
    st.error(st.session_state.explore_error)

result = st.session_state.get("explore_result")
if result and not pending:
    st.subheader("Your request")
    st.write(result["question"])
    if st.session_state.explore_history:
        with st.expander("Previous context used for this question"):
            for item in st.session_state.explore_history:
                st.write(f"**{item['role'].title()}:** {item['content']}")
    if result["status"] in {"exploratory", "validated"}:
        if not followup_mode and st.button("Ask a follow-up about this result"):
            st.session_state.explore_followup_mode = True
            st.rerun()
        validated = result["status"] == "validated"
        tool_label = (
            "Verified annual screening SQL" if result["tool"] == "run_verified_screening_trend" else
            "Verified screening SQL" if validated else
            "Parameterized Pandas" if result["tool"] == "run_pandas_aggregate"
            else "Read-only SQL"
        )
        st.subheader("Independently checked screening result" if validated
                     else "Exploratory result")
        st.write("**Tool selected by the model:**", tool_label)
        st.write("**Analysis plan:**", result["plan"])
        if validated:
            reference = result["metric_reference"]
            st.success("Every group count matched the independently calculated screening reference.")
            st.write("**Measure:**", reference["metric_name"], "· **Year:**", reference["year"])
        if result.get("cross_check"):
            st.success(
                "Numerical cross-check passed: Pandas and an independently "
                "executed SQL query returned the same counts."
            )
        query = result["query"]
        rows = query["rows"]
        if not rows:
            st.info("The query returned no rows.")
        else:
            frame = pd.DataFrame(rows)
            if validated:
                frame["coverage_percent"] = frame.apply(
                    lambda row: 100 * row["numerator"] / row["denominator"]
                    if row["denominator"] else None, axis=1
                ).round(2)
                st.dataframe(frame, hide_index=True, width="stretch")
                chart_values = frame["coverage_percent"].map(
                    lambda value: f"{value:.2f}%" if pd.notna(value) else "N/A"
                )
                if reference.get("trend"):
                    chart = px.line(
                        frame, x="group_name", y="coverage_percent",
                        markers=True, text=chart_values,
                        labels={"group_name": "Calendar year",
                                "coverage_percent": "Screening record coverage (%)"},
                    )
                else:
                    chart = px.bar(
                        frame, x="group_name", y="coverage_percent",
                        text=chart_values,
                        labels={"group_name": "Group",
                                "coverage_percent": "Screening record coverage (%)"},
                    )
                if reference.get("trend"):
                    chart.update_traces(
                        line_color="#168B85", marker_color="#168B85",
                        textposition="top center",
                    )
                    chart.update_xaxes(type="category")
                else:
                    chart.update_traces(marker_color="#168B85", textposition="outside")
                chart.update_layout(yaxis_range=[0, 105], showlegend=False)
                st.plotly_chart(chart, width="stretch")
                st.caption(reference["denominator_definition"] + " " +
                           "Missing screening documentation does not prove screening was not done. "
                           "Synthetic group differences are descriptive only.")
                if reference.get("trend"):
                    st.caption(
                        "This compares separate annual cohorts, not the same patients "
                        "followed over time. A change in synthetic record coverage does "
                        "not establish a real-world trend or a causal effect."
                    )
            else:
                st.dataframe(frame, hide_index=True, width="stretch")
                options = chart_options(frame)
                if options:
                    chart_type = st.selectbox(
                        "Chart type", options, key="explore_chart_type"
                    )
                    numeric_values = [column for column in frame
                                      if pd.api.types.is_numeric_dtype(frame[column])
                                      and not is_time_column(column)]
                    value = (st.selectbox("Chart value", numeric_values,
                                          key="explore_chart_value")
                             if len(numeric_values) > 1 else numeric_values[0])
                    try:
                        st.plotly_chart(make_chart(frame, chart_type, value), width="stretch")
                    except ValueError as exc:
                        st.info(str(exc))
        if not validated:
            st.caption(
                "Calculated from synthetic records. Query restrictions and result-shape "
                "checks passed. Numerical cross-checks, when shown, verify the counts "
                "for the selected parameters; the interpretation of the user's question "
                "was not independently audited."
            )
        with st.expander("Analysis trace: tool, query, and checks"):
            st.write("**Source tables:**", ", ".join(query["source_tables"]))
            if result["tool"] in {"run_aggregate_sql", "run_verified_screening",
                                  "run_verified_screening_trend"}:
                st.code(query["sql"], language="sql")
            else:
                st.json(query["operation"])
            st.write("**Checks performed:**")
            if result.get("cross_check"):
                st.write("**Cross-tool check:**", result["cross_check"])
            for check in result["checks"]:
                st.write("- " + check.replace(
                    "Question-to-SQL meaning", "Question-to-analysis meaning"
                ))
            for attempt in result["attempts"]:
                st.write(f'Attempt {attempt["number"]}: {attempt["status"]}')
                if attempt.get("error"):
                    st.write("Reason:", attempt["error"])
    else:
        st.info(result["message"])
        if result["attempts"]:
            with st.expander("Attempt details"):
                for attempt in result["attempts"]:
                    st.write(f'Attempt {attempt["number"]}: {attempt["status"]}')
                    if attempt.get("error"):
                        st.write("Reason:", attempt["error"])
