def render_evidence_report(result):
    """Render calculated evidence without asking a model to invent prose."""
    groups = result["groups"]
    lines = [
        f'**Adult depression screening records, {result["year"]}** — synthetic data',
        "",
    ]
    for group in groups:
        rate = group["coverage"]
        rate_text = f"{rate:.2%}" if rate is not None else "not available"
        lines.append(
            f'- **{group["group"]}:** {group["numerator"]:,} of '
            f'{group["denominator"]:,} people included had a screening '
            f'record (**{rate_text}**). '
            f'{group["not_recorded"]:,} had no qualifying screening record.'
        )
    comparison = result.get("comparison")
    if comparison:
        low = ", ".join(comparison["lowest_groups"])
        high = ", ".join(comparison["highest_groups"])
        gap = comparison["gap_percentage_points"]
        lines += ["", f'**Highest-to-lowest difference:** {gap:.2f} percentage points.']
        if gap == 0:
            lines.append("All displayed groups have the same recorded screening percentage.")
        else:
            lines.append(f'Lowest recorded percentage: **{low}**. Highest: **{high}**.')
    if result["group_by"] == "gender":
        lines += ["", "F and M are original labels in the dataset's GENDER field."]
        missing = result.get("missing_group_count")
        if missing is not None:
            lines.append(f'Eligible people with a missing GENDER value: **{missing:,}**.')
    lines += [
        "", "**Who is included?**",
        "Adults aged 18 or older on January 1, 2020, with at least one healthcare "
        "visit starting in 2020, and either no recorded death date or a death "
        "date after December 31, 2020. All visit types are included. "
        "A missing death date means no death was recorded; it does not verify survival.",
        "", "**What counts as a screening record?**",
        "At least one qualifying depression screening procedure starting in 2020 "
        "(UTC). Each person is counted once. This is a custom demonstration measure.",
        "", "**What these results cannot tell us**",
        "Missing records do not prove screening was not performed. These synthetic "
        "data do not describe a real patient population. Group comparisons are "
        "descriptive: they do not establish causes, statistical significance, "
        "or intervention effects.",
    ]
    return "\n".join(lines)
