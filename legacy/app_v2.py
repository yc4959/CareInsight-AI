"""Local V2 Streamlit pilot for independently validated model-generated SQL."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from careinsight.v2_flexible_pilot import analyze
from careinsight.v2_encounter_pilot import analyze as analyze_encounters


def analyze_question(question):
    """Select an analysis family; each tool still enforces its own scope."""
    words = question.lower()
    if ("encounter" in words or "visit" in words) and (
        "type" in words or "where" in words
    ):
        return analyze_encounters(question)
    return analyze(question)

st.set_page_config(page_title="CareInsight AI · V2 pilot", page_icon="📊", layout="wide")
st.title("CareInsight AI")
st.caption("V2 analysis pilot · Synthetic patient data · 2020")
st.info(
    "Ask about recorded adult depression or substance use screenings. "
    "This pilot supports overall, age-group, and original GENDER comparisons."
)

with st.expander("What can I ask?", expanded=False):
    st.markdown(
        "- Compare depression screening records between men and women in 2020.\n"
        "- Compare substance use screening records by age group in 2020.\n"
        "- How many adults had a substance use screening record overall in 2020?\n\n"
        "- In which encounter types were substance use screening records documented in 2020?\n\n"
        "Questions must name one screening measure and a comparison or overall total. "
        "Diagnosis, causes, treatment, other years, and combined filters are outside "
        "this pilot's verified scope."
    )

if not all(os.getenv(k) for k in (
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
)):
    st.warning("The model connection is not configured in this server session.")
    st.stop()

with st.form("v2_question"):
    question = st.text_input(
        "Your analysis question",
        placeholder="Compare substance use screening records by age group in 2020.",
    )
    submitted = st.form_submit_button("Analyze")

if submitted:
    st.session_state.v2_result = None
    st.session_state.v2_error = None
    if not question.strip():
        st.session_state.v2_error = "Enter a question about a screening record measure."
    else:
        try:
            with st.spinner("Planning, running SQL, and independently checking counts..."):
                st.session_state.v2_result = analyze_question(question.strip())
        except (ValueError, RuntimeError) as exc:
            st.session_state.v2_error = str(exc)
        except Exception:
            st.session_state.v2_error = (
                "The analysis could not be completed. No result was published."
            )

if st.session_state.get("v2_error"):
    st.error(st.session_state.v2_error)

result = st.session_state.get("v2_result")
if result:
    st.subheader("What we found")
    st.success("Independent baseline validation passed.")
    st.write("**Your question:**", result["question"])
    if "reference" in result:
        reference = result["reference"]
        st.write("**Measure:** Substance use screening procedure records")
        st.write("**Comparison:** Linked encounter type")
        a, b, c = st.columns(3)
        a.metric("Eligible adults", reference["eligible_adults"])
        b.metric("Qualifying procedure records", reference["total_procedure_records"])
        c.metric("Patients with a record", reference["unique_patients_overall"])
        frame = pd.DataFrame(result["groups"])
        st.dataframe(frame.rename(columns={
            "encounter_class": "Encounter type",
            "procedure_records": "Procedure records",
            "unique_patients": "Distinct patients",
        }), hide_index=True, width="stretch")
        chart = px.bar(
            frame, x="encounter_class", y="procedure_records",
            text="procedure_records", custom_data=["unique_patients"],
            labels={"encounter_class": "Encounter type",
                    "procedure_records": "Procedure records"},
        )
        chart.update_traces(
            marker_color="#168B85", textposition="outside",
            hovertemplate="%{x}: %{y} records<br>%{customdata[0]} distinct patients<extra></extra>",
        )
        chart.update_layout(showlegend=False)
        st.plotly_chart(chart, width="stretch")
        st.caption(
            "The chart counts qualifying procedure records linked to each encounter "
            "type. A patient can appear in more than one type; distinct patient counts "
            "across types must not be added. The source description for code 713106006 "
            "is 'Screening for drug abuse (procedure)'."
        )
    else:
        st.write(
            "**Measure:**", "Depression screening records" if result["metric"] == "depression"
            else "Substance use screening records"
        )
        st.write("**Comparison:**", {
            "overall": "All eligible adults",
            "age_group": "Age groups",
            "gender": "Original GENDER field",
        }[result["group_by"]])

        frame = pd.DataFrame(result["groups"])
        display = frame.rename(columns={
            "group": "Group", "denominator": "Eligible adults",
            "numerator": "With a screening record", "coverage": "Percentage",
        })
        display["Percentage"] = display["Percentage"].map(lambda x: f"{x:.2%}")
        st.dataframe(display, hide_index=True, width="stretch")

        chart = px.bar(
            frame, x="group", y="coverage", text=frame["coverage"].map(lambda x: f"{x:.2%}"),
            custom_data=["numerator", "denominator"],
            labels={"group": "Group", "coverage": "Share with a screening record"},
        )
        chart.update_traces(
            marker_color="#168B85", textposition="outside",
            hovertemplate=(
                "Group: %{x}<br>With a record: %{customdata[0]}<br>"
                "Eligible adults: %{customdata[1]}<br>Share: %{y:.2%}<extra></extra>"
            ),
        )
        chart.update_layout(yaxis_range=[0, 1], yaxis_tickformat=".0%", showlegend=False)
        st.plotly_chart(chart, width="stretch")

    st.caption(
        "Adults aged 18+ on 2020-01-01, with at least one 2020 encounter and no "
        "recorded death before 2021. A missing screening record does not prove "
        "screening was not performed. These synthetic data do not describe real "
        "patients; comparisons do not establish causes or statistical significance."
    )

    with st.expander("Analysis trace: plan, SQL, and checks"):
        st.write("**Model plan:**", result["plan"])
        st.code(result["query"]["sql"], language="sql")
        st.write("**Source tables:**", ", ".join(result["query"]["source_tables"]))
        st.write("**Independent count check:** passed")
        for attempt in result["attempts"]:
            st.write(f'Attempt {attempt["number"]}: {attempt["status"]}')
            if attempt.get("error"):
                st.write("Reason:", attempt["error"])
