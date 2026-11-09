import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from careinsight.summary_tool import get_screening_summary

st.set_page_config(
    page_title="CareInsight AI",
    page_icon="📊",
    layout="wide",
)

st.title("CareInsight AI")
st.caption("Population Health Analytics · Synthea Demo · 2020")
st.info(
    "Synthetic patient data · Custom screening record metric · "
    "Not an official quality measure"
)

with st.sidebar:
    st.header("Analysis settings")
    st.selectbox("Measurement year", [2020])
    grouping = st.radio(
        "Compare populations",
        ["age_group", "gender"],
        format_func=lambda value: {
            "age_group": "Age group",
            "gender": "GENDER field",
        }[value],
    )
    st.caption(
        "All views use the same eligible population. "
        "Changing the grouping does not change the denominator."
    )

try:
    overall_result = get_screening_summary(group_by="overall")
    grouped_result = get_screening_summary(group_by=grouping)
except (OSError, ValueError, KeyError):
    st.error("Unable to load the analysis. Check the source CSV files.")
    st.stop()

overall = overall_result["groups"][0]
columns = st.columns(4)

columns[0].metric("Eligible patients", f'{overall["denominator"]:,}')
columns[1].metric("Screening recorded", f'{overall["numerator"]:,}')
columns[2].metric("No screening record", f'{overall["not_recorded"]:,}')
columns[3].metric("Record coverage", f'{overall["coverage"]:.2%}')

st.caption("No screening record does not mean screening was not performed.")

st.subheader("Screening record coverage by population")
frame = pd.DataFrame(grouped_result["groups"])

figure = go.Figure(go.Bar(
    x=frame["group"],
    y=frame["coverage"],
    text=[f"{value:.2%}" for value in frame["coverage"]],
    textposition="outside",
    marker_color="#168B85",
    customdata=frame[["numerator", "denominator"]].to_numpy(),
    hovertemplate=(
        "Group: %{x}<br>"
        "Coverage: %{y:.2%}<br>"
        "Screening recorded: %{customdata[0]}<br>"
        "Eligible patients: %{customdata[1]}"
        "<extra></extra>"
    ),
))
figure.update_layout(
    height=380,
    template="plotly_white",
    xaxis_title="Age group" if grouping == "age_group" else "GENDER",
    yaxis_title="Screening record coverage",
    yaxis_range=[0, 1],
    yaxis_tickformat=".0%",
    showlegend=False,
    margin=dict(t=35, b=35),
)
st.plotly_chart(figure, width="stretch")

comparison = grouped_result["comparison"]
if comparison:
    lowest = ", ".join(comparison["lowest_groups"])
    highest = ", ".join(comparison["highest_groups"])
    gap = comparison["gap_percentage_points"]
    st.write(
        f"**Lowest observed coverage:** {lowest}. "
        f"**Highest observed coverage:** {highest}. "
        f"**Highest-to-lowest gap:** {gap:.2f} percentage points."
    )

st.caption(
    "Descriptive comparison only. Statistical significance and causes "
    "have not been established."
)

table = frame.rename(columns={
    "group": "Group",
    "numerator": "Screening recorded",
    "denominator": "Eligible patients",
    "not_recorded": "No screening record",
    "coverage": "Coverage",
})
table["Coverage"] = table["Coverage"].map(lambda value: f"{value:.2%}")
st.dataframe(
    table[[
        "Group", "Screening recorded", "Eligible patients",
        "No screening record", "Coverage",
    ]],
    hide_index=True,
)

with st.expander("Metric definition and limitations"):
    st.write("**Denominator:**", grouped_result["denominator_definition"])
    st.write(
        "**Numerator:** Eligible patients with at least one procedure "
        "record in 2020 using code 171207006, 454711000124102, or 715252007. "
        "Each patient is counted once."
    )
    st.write(
        "**Time window:** 2020-01-01 inclusive to 2021-01-01 exclusive, UTC."
    )
    st.write("**Grouping source:**", grouped_result["group_source"])
    if grouped_result["missing_group_count"] is not None:
        st.write(
            "**Missing grouping values:**",
            grouped_result["missing_group_count"],
        )
    for limitation in grouped_result["limitations"]:
        st.write("- " + limitation)


from careinsight.chat_ui import render_chat
render_chat()
