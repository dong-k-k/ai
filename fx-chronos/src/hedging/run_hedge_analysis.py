from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from src.hedging.forecast_provider import (
    ForecastScenario,
    ScenarioSource,
    load_forecast_scenario_from_csv,
)
from src.hedging.hedge_analysis import ExposureSide, FxExposure, HedgeAnalysisResult, analyze_fx_exposure


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "configs" / "hedge_example.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="공통 환율 시나리오를 지급·수취 계약의 원화 금액으로 변환합니다."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="환위험 분석 JSON 설정 경로",
    )
    return parser.parse_args()


def load_json_config(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    required_sections = {"contract", "forecast", "output"}
    missing_sections = required_sections - set(config)
    if missing_sections:
        raise ValueError(f"환위험 설정에 필수 구역이 없습니다: {sorted(missing_sections)}")
    return config


def resolve_project_path(path_value: str) -> Path:
    """설정 경로가 프로젝트 바깥으로 벗어나지 않도록 제한한다."""
    resolved = (PROJECT_DIR / path_value).resolve()
    if not resolved.is_relative_to(PROJECT_DIR.resolve()):
        raise ValueError(f"프로젝트 밖의 경로는 사용할 수 없습니다: {path_value}")
    return resolved


def build_exposure(contract: dict[str, Any]) -> FxExposure:
    try:
        side = ExposureSide(contract["side"])
    except ValueError as exc:
        raise ValueError("contract.side는 payment 또는 receipt여야 합니다.") from exc
    return FxExposure(
        currency_pair=str(contract["currency_pair"]),
        side=side,
        foreign_amount=float(contract["foreign_amount"]),
        settlement_date=date.fromisoformat(str(contract["settlement_date"])),
        reference_rate=float(contract["reference_rate"]),
        hedged_amount=(
            float(contract["hedged_amount"])
            if contract.get("hedged_amount") is not None
            else None
        ),
        hedged_ratio=(
            float(contract["hedged_ratio"])
            if contract.get("hedged_ratio") is not None
            else None
        ),
        hedge_rate=(
            float(contract["hedge_rate"])
            if contract.get("hedge_rate") is not None
            else None
        ),
    )


def build_forecast(forecast_config: dict[str, Any]) -> ForecastScenario:
    try:
        source = ScenarioSource(forecast_config["scenario_source"])
    except ValueError as exc:
        allowed = [source.value for source in ScenarioSource]
        raise ValueError(f"지원하지 않는 scenario_source입니다. 허용값={allowed}") from exc
    metrics = {
        str(name): float(value)
        for name, value in forecast_config.get("validation_metrics", {}).items()
    }
    return load_forecast_scenario_from_csv(
        resolve_project_path(str(forecast_config["csv_path"])),
        requested_origin=forecast_config["requested_origin"],
        model_name=str(forecast_config["model_name"]),
        scenario_source=source,
        point_column=str(forecast_config["point_column"]),
        currency_pair=str(forecast_config.get("currency_pair", "USD/KRW")),
        unit=str(forecast_config["unit"]),
        lower_column=forecast_config.get("lower_column"),
        median_column=forecast_config.get("median_column"),
        upper_column=forecast_config.get("upper_column"),
        validation_metrics=metrics,
        warning=str(forecast_config.get("warning", "")),
    )


def result_to_json_record(
    result: HedgeAnalysisResult,
    *,
    example_only: bool,
) -> dict[str, Any]:
    record = asdict(result)
    record["side"] = result.side.value
    record["settlement_date"] = result.settlement_date.isoformat()
    record["example_only"] = example_only
    return record


def result_to_csv_rows(
    result: HedgeAnalysisResult,
    *,
    example_only: bool,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario in result.scenarios:
        rows.append(
            {
                "example_only": example_only,
                "currency_pair": result.currency_pair,
                "side": result.side.value,
                "settlement_date": result.settlement_date.isoformat(),
                "foreign_amount": result.foreign_amount,
                "hedged_amount": result.hedged_amount,
                "unhedged_amount": result.unhedged_amount,
                "hedge_ratio": result.hedge_ratio,
                "forecast_model_name": result.forecast_model_name,
                "scenario_source": result.scenario_source,
                **asdict(scenario),
            }
        )
    return rows


def save_outputs_without_overwrite(
    result: HedgeAnalysisResult,
    output_config: dict[str, Any],
    *,
    example_only: bool,
) -> tuple[Path, Path]:
    json_path = resolve_project_path(str(output_config["json_path"]))
    csv_path = resolve_project_path(str(output_config["csv_path"]))
    existing_paths = [path for path in (json_path, csv_path) if path.exists()]
    if existing_paths:
        raise FileExistsError(f"기존 환위험 분석 결과를 덮어쓰지 않습니다: {existing_paths}")

    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            result_to_json_record(result, example_only=example_only),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    csv_rows = result_to_csv_rows(result, example_only=example_only)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    return json_path, csv_path


def main() -> None:
    args = parse_args()
    config = load_json_config(args.config.resolve())
    example_only = bool(config.get("example_only", False))
    exposure = build_exposure(config["contract"])
    forecast = build_forecast(config["forecast"])
    result = analyze_fx_exposure(exposure, forecast)
    json_path, csv_path = save_outputs_without_overwrite(
        result,
        config["output"],
        example_only=example_only,
    )

    print(f"example_only: {example_only}")
    print(f"side: {result.side.value}")
    print(f"settlement_date: {result.settlement_date}")
    print(f"foreign_amount: {result.foreign_amount:,.2f}")
    print(f"hedged_amount: {result.hedged_amount:,.2f}")
    print(f"unhedged_amount: {result.unhedged_amount:,.2f}")
    print(f"risk_direction: {result.risk_direction}")
    for scenario in result.scenarios:
        print(
            f"{scenario.scenario_name}: rate={scenario.fx_rate:,.4f}, "
            f"total_krw={scenario.total_krw_amount:,.0f}, "
            f"favorable_pnl={scenario.favorable_pnl_vs_reference_krw:,.0f}"
        )
    print(f"warnings: {len(result.warnings)}")
    print(f"saved_json: {json_path}")
    print(f"saved_csv: {csv_path}")


if __name__ == "__main__":
    main()
