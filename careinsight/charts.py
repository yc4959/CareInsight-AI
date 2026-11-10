"""Render aggregate results without letting the model execute plotting code."""

import pandas as pd
import plotly.express as px


TEAL = "#168B85"
TIME_COLUMNS = {"year", "calendar_year", "month", "date"}


def is_time_column(name: str) -> bool:
    name = name.lower()
    return name in TIME_COLUMNS or name.endswith("_year") or name.endswith("_month")


def _columns(frame):
    categories = [c for c in frame if not pd.api.types.is_numeric_dtype(frame[c])
                  or is_time_column(c)]
    values = [c for c in frame if pd.api.types.is_numeric_dtype(frame[c])
              and not is_time_column(c)]
    return categories, values


def chart_options(frame: pd.DataFrame) -> list[str]:
    """Only offer chart forms supported by the returned aggregate columns."""
    if frame.empty or len(frame) > 50:
        return []
    categories, numeric = _columns(frame)
    options = []
    if len(categories) >= 1 and len(numeric) >= 1 and len(frame) > 1:
        options.append("Bar chart")
    time_columns = [c for c in categories if is_time_column(c)]
    if time_columns and numeric and len(frame) > 1:
        options.append("Line chart")
    if len(categories) >= 2 and numeric and len(frame) > 1:
        options.append("Heatmap")
    return options


def make_chart(frame: pd.DataFrame, kind: str, value: str | None = None):
    """Build a figure solely from aggregate rows and approved chart forms."""
    if kind not in chart_options(frame):
        raise ValueError("This result does not support the requested chart.")
    categories, numeric = _columns(frame)
    value = value or numeric[-1]
    if value not in numeric:
        raise ValueError("The chart value must be a numeric result column.")
    if kind == "Bar chart":
        category = next((c for c in categories if is_time_column(c)), categories[0])
        if len(categories) >= 2:
            series = next(c for c in categories if c != category)
            chart_frame = frame.copy()
            chart_frame[category] = chart_frame[category].astype(str)
            chart_frame[series] = chart_frame[series].astype(str)
            fig = px.bar(
                chart_frame, x=category, y=value, color=series, barmode="group",
                labels={value: value.replace("_", " ").title()},
            )
            fig.update_xaxes(type="category")
            return fig
        chart_frame = frame.copy()
        chart_frame["_short_label"] = chart_frame[category].astype(str).map(
            lambda label: label if len(label) <= 48 else label[:45] + "..."
        )
        fig = px.bar(
            chart_frame, x=value, y="_short_label", orientation="h", text=value,
            custom_data=[category], labels={"_short_label": "", value: value.replace("_", " ").title()},
        )
        fig.update_traces(marker_color=TEAL, textposition="outside",
                          hovertemplate="%{customdata[0]}<br>%{x}<extra></extra>")
        fig.update_layout(showlegend=False, yaxis_autorange="reversed",
                          height=max(400, 48 * len(frame)),
                          margin=dict(l=20, r=60, t=20, b=30))
        fig.update_yaxes(type="category")
        return fig
    if kind == "Line chart":
        time_col = next(c for c in categories if is_time_column(c))
        chart_frame = frame.copy().sort_values(time_col)
        color = next((c for c in categories if c != time_col), None)
        fig = px.line(chart_frame, x=time_col, y=value, color=color, markers=True,
                      labels={value: value.replace("_", " ").title()})
        if color is None:
            fig.update_traces(line_color=TEAL, marker_color=TEAL)
        fig.update_xaxes(type="category")
        return fig
    x_col, y_col = categories[:2]
    if frame.duplicated([x_col, y_col]).any():
        raise ValueError("A heatmap needs one value per pair of groups.")
    chart_frame = frame.copy()
    chart_frame[x_col] = chart_frame[x_col].astype(str)
    chart_frame[y_col] = chart_frame[y_col].astype(str)
    matrix = chart_frame.pivot(index=y_col, columns=x_col, values=value)
    fig = px.imshow(matrix, aspect="auto", text_auto=True,
                    color_continuous_scale="Teal", labels={"color": value.replace("_", " ").title()})
    fig.update_layout(xaxis_title=x_col.replace("_", " ").title(),
                      yaxis_title=y_col.replace("_", " ").title())
    return fig
