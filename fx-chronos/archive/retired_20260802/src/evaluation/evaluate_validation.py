from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.evaluation.evaluate import build_grouped_metrics, calculate_metrics, save_without_overwrite


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
BACKTEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_walk_forward_h20_monthly_1997_2025.csv"
)
MANIFEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "core"
    / "usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv"
)
OUTPUT_DIR = PROJECT_DIR / "outputs" / "metrics" / "core"
OUTPUT_STEM = "usd_krw_walk_forward_h20_monthly_validation_2018_2021"
EXPECTED_ORIGINS = 48
EXPECTED_ROWS_PER_ORIGIN = 20


def load_validation_rows(backtest_path: Path, manifest_path: Path) -> pd.DataFrame:
    """Select only origins assigned to validation in the locked split manifest."""
    manifest = pd.read_csv(manifest_path)
    if manifest["requested_origin"].duplicated().any():
        raise RuntimeError("분할 명세에 중복 요청 기준일이 있습니다.")

    validation_origins = manifest.loc[
        manifest["split"].eq("validation"), "requested_origin"
    ].tolist()
    if len(validation_origins) != EXPECTED_ORIGINS:
        raise RuntimeError(
            f"Validation 기준일 수가 예상과 다릅니다: "
            f"실제={len(validation_origins)}, 예상={EXPECTED_ORIGINS}"
        )

    backtest = pd.read_csv(
        backtest_path,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    validation = backtest[backtest["requested_origin"].isin(validation_origins)].copy()
    actual_origins = set(validation["requested_origin"].unique())
    if actual_origins != set(validation_origins):
        missing = sorted(set(validation_origins) - actual_origins)
        raise RuntimeError(f"백테스트에 Validation 기준일이 없습니다: {missing}")

    counts = validation.groupby("requested_origin")["forecast_step"].agg(["size", "nunique"])
    if ((counts["size"] != EXPECTED_ROWS_PER_ORIGIN) | (counts["nunique"] != EXPECTED_ROWS_PER_ORIGIN)).any():
        raise RuntimeError("Validation 기준일별 행 또는 forecast_step이 20개가 아닙니다.")
    return validation.sort_values(
        ["forecast_origin_date", "forecast_step"]
    ).reset_index(drop=True)


def main() -> None:
    output_paths = {
        "summary": OUTPUT_DIR / f"{OUTPUT_STEM}_summary.csv",
        "by_origin": OUTPUT_DIR / f"{OUTPUT_STEM}_by_origin.csv",
        "by_lead": OUTPUT_DIR / f"{OUTPUT_STEM}_by_lead.csv",
    }
    for output_path in output_paths.values():
        if output_path.exists():
            raise FileExistsError(f"기존 Validation 평가를 덮어쓰지 않습니다: {output_path}")

    validation = load_validation_rows(BACKTEST_PATH, MANIFEST_PATH)
    summary = pd.DataFrame(
        [
            {
                "split": "validation",
                "horizon": EXPECTED_ROWS_PER_ORIGIN,
                "origins": EXPECTED_ORIGINS,
                **calculate_metrics(validation),
            }
        ]
    )
    by_origin = build_grouped_metrics(validation, "forecast_origin_date")
    by_lead = build_grouped_metrics(validation, "forecast_step")

    save_without_overwrite(summary, output_paths["summary"])
    save_without_overwrite(by_origin, output_paths["by_origin"])
    save_without_overwrite(by_lead, output_paths["by_lead"])
    print(f"Saved Validation summary to {output_paths['summary']}")
    print(f"Saved Validation origin metrics to {output_paths['by_origin']}")
    print(f"Saved Validation lead metrics to {output_paths['by_lead']}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
