from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from evaluate import save_without_overwrite
from evaluate_shrunk_ensemble import point_metrics


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_shrunk_ensemble_h20_ctx756_validation_2018_2021.csv"
)
SELECTION_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "usd_krw_shrunk_ensemble_h20_ctx756_validation_2018_2021_selection.json"
)
OUTPUT_STEM = "usd_krw_shrunk_ensemble_h20_ctx756_validation_2018_2021_stability"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "metrics"
ORIGIN_PATH = OUTPUT_DIR / f"{OUTPUT_STEM}_by_origin.csv"
YEAR_PATH = OUTPUT_DIR / f"{OUTPUT_STEM}_by_year.csv"
SEGMENT_PATH = OUTPUT_DIR / f"{OUTPUT_STEM}_by_lead_segment.csv"
EXCLUSION_PATH = OUTPUT_DIR / f"{OUTPUT_STEM}_top_origin_exclusion.csv"
SUMMARY_PATH = OUTPUT_DIR / f"{OUTPUT_STEM}_summary.json"
EXPECTED_SELECTED_ALPHA = 0.5
EXCLUSION_COUNTS = (1, 3, 5)


def load_selected_forecast() -> pd.DataFrame:
    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    if selection["final_test_used_for_selection"] is not False:
        raise RuntimeError("α 선택에 최종 Test가 사용된 것으로 기록돼 있습니다.")
    selected_alpha = float(selection["selected_alpha"])
    if selected_alpha != EXPECTED_SELECTED_ALPHA:
        raise RuntimeError(f"선택된 α가 예상과 다릅니다: {selected_alpha}")

    forecast = pd.read_csv(
        INPUT_PATH,
        parse_dates=["requested_origin", "forecast_origin_date", "target_date"],
    )
    selected = forecast[forecast["alpha"].eq(selected_alpha)].copy()
    if len(selected) != 48 * 20:
        raise RuntimeError(f"선택된 α의 행 수가 예상과 다릅니다: {len(selected)}")
    if selected.isna().any().any():
        raise RuntimeError("선택된 α 예측에 결측값이 있습니다.")
    if selected.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("선택된 α 예측에 중복 행이 있습니다.")
    return selected.sort_values(
        ["requested_origin", "forecast_step"]
    ).reset_index(drop=True)


def build_origin_contributions(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for origin, group in selected.groupby("requested_origin", sort=True):
        actual = group["actual_value"].astype(float)
        ensemble_error = group["ensemble_forecast"].astype(float) - actual
        random_walk_error = group["random_walk_forecast"].astype(float) - actual
        metrics = point_metrics(group)
        rows.append(
            {
                "requested_origin": origin,
                "year": int(origin.year),
                **metrics,
                "mae_error_reduction_sum": float(
                    random_walk_error.abs().sum() - ensemble_error.abs().sum()
                ),
                "squared_error_reduction_sum": float(
                    (random_walk_error**2).sum() - (ensemble_error**2).sum()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("requested_origin").reset_index(drop=True)


def build_year_metrics(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year, group in selected.groupby(selected["requested_origin"].dt.year, sort=True):
        rows.append(
            {
                "year": int(year),
                "origins": int(group["requested_origin"].nunique()),
                **point_metrics(group),
            }
        )
    return pd.DataFrame(rows)


def build_segment_metrics(selected: pd.DataFrame) -> pd.DataFrame:
    segments = (
        ("D+1~D+5", 1, 5),
        ("D+6~D+10", 6, 10),
        ("D+11~D+20", 11, 20),
    )
    rows: list[dict[str, object]] = []
    for name, start, end in segments:
        group = selected[selected["forecast_step"].between(start, end)]
        rows.append(
            {
                "lead_segment": name,
                "lead_start": start,
                "lead_end": end,
                "origins": int(group["requested_origin"].nunique()),
                **point_metrics(group),
            }
        )
    return pd.DataFrame(rows)


def build_exclusion_metrics(
    selected: pd.DataFrame, origins: pd.DataFrame
) -> pd.DataFrame:
    rankings = {
        "mae_contribution": origins.sort_values(
            "mae_error_reduction_sum", ascending=False
        ),
        "rmse_contribution": origins.sort_values(
            "squared_error_reduction_sum", ascending=False
        ),
    }
    rows: list[dict[str, object]] = []
    for basis, ranking in rankings.items():
        for count in EXCLUSION_COUNTS:
            removed = ranking.head(count)["requested_origin"].tolist()
            remaining = selected[~selected["requested_origin"].isin(removed)]
            rows.append(
                {
                    "exclusion_basis": basis,
                    "excluded_origin_count": count,
                    "excluded_origins": "|".join(
                        origin.strftime("%Y-%m-%d") for origin in removed
                    ),
                    "remaining_origins": int(remaining["requested_origin"].nunique()),
                    **point_metrics(remaining),
                }
            )
    return pd.DataFrame(rows)


def build_summary(
    selected: pd.DataFrame,
    origins: pd.DataFrame,
    years: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> dict[str, object]:
    overall = point_metrics(selected)
    positive_mae = origins[origins["mae_error_reduction_sum"] > 0]
    total_positive_mae = float(positive_mae["mae_error_reduction_sum"].sum())
    top_mae = origins.sort_values("mae_error_reduction_sum", ascending=False)
    return {
        "selected_alpha": EXPECTED_SELECTED_ALPHA,
        "selection_split": "validation_2018_2021",
        "final_test_used": False,
        "overall": overall,
        "origin_count": int(origins["requested_origin"].nunique()),
        "origin_mae_win_count": int((origins["ensemble_mae"] < origins["random_walk_mae"]).sum()),
        "origin_rmse_win_count": int((origins["ensemble_rmse"] < origins["random_walk_rmse"]).sum()),
        "median_origin_mae_improvement_percent": float(
            origins["mae_improvement_vs_random_walk_percent"].median()
        ),
        "median_origin_rmse_improvement_percent": float(
            origins["rmse_improvement_vs_random_walk_percent"].median()
        ),
        "top_1_share_of_positive_mae_reduction": (
            float(top_mae.head(1)["mae_error_reduction_sum"].sum() / total_positive_mae)
            if total_positive_mae > 0
            else None
        ),
        "top_3_share_of_positive_mae_reduction": (
            float(top_mae.head(3)["mae_error_reduction_sum"].sum() / total_positive_mae)
            if total_positive_mae > 0
            else None
        ),
        "years_improving_both_mae_and_rmse": int(
            (
                (years["ensemble_mae"] < years["random_walk_mae"])
                & (years["ensemble_rmse"] < years["random_walk_rmse"])
            ).sum()
        ),
        "robust_after_each_registered_exclusion": bool(
            (
                (exclusions["ensemble_mae"] <= exclusions["random_walk_mae"])
                & (exclusions["ensemble_rmse"] <= exclusions["random_walk_rmse"])
            ).all()
        ),
    }


def main() -> None:
    output_paths = (ORIGIN_PATH, YEAR_PATH, SEGMENT_PATH, EXCLUSION_PATH, SUMMARY_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 안정성 분석을 덮어쓰지 않습니다: {existing}")

    selected = load_selected_forecast()
    origins = build_origin_contributions(selected)
    years = build_year_metrics(selected)
    segments = build_segment_metrics(selected)
    exclusions = build_exclusion_metrics(selected, origins)
    summary = build_summary(selected, origins, years, exclusions)

    save_without_overwrite(origins, ORIGIN_PATH)
    save_without_overwrite(years, YEAR_PATH)
    save_without_overwrite(segments, SEGMENT_PATH)
    save_without_overwrite(exclusions, EXCLUSION_PATH)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Year metrics")
    print(years.to_string(index=False))
    print("\nLead segment metrics")
    print(segments.to_string(index=False))
    print("\nTop-origin exclusion metrics")
    print(exclusions.to_string(index=False))
    print("\nStability summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
