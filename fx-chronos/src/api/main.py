from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request

from src.api.forecast_service import ForecastService
from src.api.scheduler import create_scheduler
from src.api.schemas import (
    ApiExposureSide,
    ForecastPointResponse,
    FxForecastResponse,
    HedgeAnalysisRequest,
    HedgeAnalysisResponse,
)
from src.hedging.hedge_analysis import ExposureSide, FxExposure, analyze_fx_exposure


LOGGER = logging.getLogger(__name__)


def create_app(
    *,
    forecast_service: ForecastService | None = None,
    enable_scheduler: bool = True,
) -> FastAPI:
    service = forecast_service or ForecastService()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(service.initialize)
        application.state.forecast_service = service
        scheduler = create_scheduler(service) if enable_scheduler else None
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    application = FastAPI(title="FX Chronos Internal API", lifespan=lifespan)

    def get_forecast_service(request: Request) -> ForecastService:
        return request.app.state.forecast_service

    @application.post(
        "/internal/hedge-analysis",
        response_model=HedgeAnalysisResponse,
    )
    def hedge_analysis(
        payload: HedgeAnalysisRequest,
        active_service: ForecastService = Depends(get_forecast_service),
    ) -> HedgeAnalysisResponse:
        try:
            side = (
                ExposureSide.PAYMENT
                if payload.side is ApiExposureSide.PAYABLE
                else ExposureSide.RECEIPT
            )
            exposure = FxExposure(
                currency_pair=payload.currency_pair,
                side=side,
                foreign_amount=payload.foreign_amount,
                settlement_date=payload.settlement_date,
                reference_rate=payload.reference_rate,
                hedged_amount=payload.hedged_amount,
                hedge_rate=payload.hedge_rate,
            )
            forecast = active_service.forecast_for_settlement(payload.settlement_date)
            result = analyze_fx_exposure(exposure, forecast)
            return HedgeAnalysisResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception:
            LOGGER.exception("Unexpected hedge analysis failure")
            raise HTTPException(status_code=500, detail="Internal hedge analysis failure") from None

    @application.get(
        "/internal/fx-forecast",
        response_model=FxForecastResponse,
    )
    def fx_forecast(
        active_service: ForecastService = Depends(get_forecast_service),
    ) -> FxForecastResponse:
        try:
            generated_at, forecast = active_service.h90_forecast()
            if (
                forecast.lower_scenario is None
                or forecast.median_scenario is None
                or forecast.upper_scenario is None
            ):
                raise RuntimeError("H90 예측에 분위수 시나리오가 없습니다.")
            points = tuple(
                ForecastPointResponse(
                    date=forecast_date,
                    point=point,
                    lower=lower,
                    median=median,
                    upper=upper,
                )
                for forecast_date, point, lower, median, upper in zip(
                    forecast.forecast_dates,
                    forecast.point_forecast,
                    forecast.lower_scenario,
                    forecast.median_scenario,
                    forecast.upper_scenario,
                    strict=True,
                )
            )
            return FxForecastResponse(
                currency_pair=forecast.currency_pair,
                forecast_origin=forecast.forecast_origin,
                horizon=forecast.prediction_length,
                unit=forecast.unit,
                model_name=forecast.model_name,
                generated_at=generated_at,
                forecast=points,
                warnings=(forecast.warning.strip(),),
            )
        except Exception:
            LOGGER.exception("Unexpected forecast service failure")
            raise HTTPException(status_code=500, detail="Internal forecast service failure") from None

    return application


app = create_app()
