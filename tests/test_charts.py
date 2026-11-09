import pandas as pd
import pytest

from careinsight.charts import chart_options, make_chart


def test_two_dimension_counts_support_line_and_heatmap():
    frame = pd.DataFrame({
        "year": [2019, 2019, 2020, 2020],
        "visit_type": ["wellness", "outpatient"] * 2,
        "records": [10, 4, 12, 6],
    })
    assert chart_options(frame) == ["Bar chart", "Line chart", "Heatmap"]
    assert len(make_chart(frame, "Line chart", "records").data) == 2
    heatmap = make_chart(frame, "Heatmap", "records")
    assert heatmap.data[0].z.shape == (2, 2)


def test_heatmap_refuses_duplicate_group_pairs():
    frame = pd.DataFrame({
        "year": [2020, 2020], "visit_type": ["wellness", "wellness"],
        "records": [10, 12],
    })
    with pytest.raises(ValueError, match="one value per pair"):
        make_chart(frame, "Heatmap", "records")
