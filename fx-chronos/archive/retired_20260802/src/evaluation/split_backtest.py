from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "evaluation.json"
BACKTEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_walk_forward_h20_monthly_1997_2025.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "core"
    / "usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv"
)
SPLIT_NAMES = ("development_history", "validation", "final_test")


def load_split_config(config_path: Path) -> dict[str, object]:
    """Load the fixed chronological split policy."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config["finetuning_plan"]["fixed_split"]


def build_split_manifest(backtest: pd.DataFrame, split_config: dict[str, object]) -> pd.DataFrame:
    """Assign an origin only when all of its target dates fit inside one split."""
    required_columns = {
        "requested_origin",
        "forecast_origin_date",
        "forecast_step",
        "target_date",
    }
    missing_columns = required_columns - set(backtest.columns)
    if missing_columns:
        raise RuntimeError(f"분할 입력에 필수 열이 없습니다: {sorted(missing_columns)}")
    if backtest[list(required_columns)].isna().any().any():
        raise RuntimeError("분할 입력에 결측값이 있습니다.")

    origin_rows = backtest.groupby("requested_origin", sort=True).agg(
        forecast_origin_date=("forecast_origin_date", "first"),
        forecast_origin_date_count=("forecast_origin_date", "nunique"),
        target_start=("target_date", "min"),
        target_end=("target_date", "max"),
        forecast_rows=("forecast_step", "size"),
        forecast_step_count=("forecast_step", "nunique"),
    )
    if (origin_rows["forecast_origin_date_count"] != 1).any():
        raise RuntimeError("하나의 요청 기준일이 여러 실제 기준일에 연결되어 있습니다.")
    if ((origin_rows["forecast_rows"] != 20) | (origin_rows["forecast_step_count"] != 20)).any():
        raise RuntimeError("기준일별 예측 행 또는 forecast_step이 20개가 아닙니다.")

    manifest_rows: list[dict[str, object]] = []
    for requested_origin, row in origin_rows.iterrows():
        matching_splits: list[str] = []
        for split_name in SPLIT_NAMES:
            section = split_config[split_name]
            if (
                row["target_start"] >= pd.Timestamp(section["target_start"])
                and row["target_end"] <= pd.Timestamp(section["target_end"])
            ):
                matching_splits.append(split_name)

        if len(matching_splits) > 1:
            raise RuntimeError(f"하나의 기준일이 여러 분할에 배정됐습니다: {requested_origin}")
        split = matching_splits[0] if matching_splits else "excluded"
        reason = (
            "all_target_dates_contained"
            if matching_splits
            else "target_dates_cross_split_boundary"
        )
        manifest_rows.append(
            {
                "requested_origin": requested_origin,
                "forecast_origin_date": pd.Timestamp(row["forecast_origin_date"]),
                "target_start": pd.Timestamp(row["target_start"]),
                "target_end": pd.Timestamp(row["target_end"]),
                "forecast_rows": int(row["forecast_rows"]),
                "split": split,
                "assignment_reason": reason,
            }
        )

    manifest = pd.DataFrame.from_records(manifest_rows)
    actual_counts = manifest["split"].value_counts().to_dict()
    for split_name in SPLIT_NAMES:
        expected_count = int(split_config[split_name]["expected_monthly_origins"])
        if actual_counts.get(split_name, 0) != expected_count:
            raise RuntimeError(
                f"분할 기준일 수가 설정과 다릅니다: {split_name}, "
                f"실제={actual_counts.get(split_name, 0)}, 예상={expected_count}"
            )

    excluded = manifest.loc[manifest["split"] == "excluded", "requested_origin"].tolist()
    if excluded != split_config["known_excluded_requested_origins"]:
        raise RuntimeError(
            f"제외 기준일이 설정과 다릅니다: 실제={excluded}, "
            f"예상={split_config['known_excluded_requested_origins']}"
        )
    return manifest


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 분할 명세를 덮어쓰지 않습니다: {OUTPUT_PATH}")

    split_config = load_split_config(CONFIG_PATH)
    backtest = pd.read_csv(
        BACKTEST_PATH,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    manifest = build_split_manifest(backtest, split_config)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    print(f"Saved fixed split manifest to {OUTPUT_PATH}")
    print(manifest["split"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
