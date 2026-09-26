from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx


class _SchemaModel:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)

    def model_dump(self) -> dict[str, Any]:
        return dict(self.__dict__)


try:
    import app.schemas  # noqa: F401
except ModuleNotFoundError:
    schema_stub = ModuleType("app.schemas")
    for model_name in ("TrialRecord", "EvidenceItem", "CohortResult", "NumericFact"):
        setattr(schema_stub, model_name, type(model_name, (_SchemaModel,), {}))
    sys.modules["app.schemas"] = schema_stub


from app.registry.client import (  # noqa: E402
    ClinicalTrialsClient,
    InvalidNCTId,
    RegistryNotFound,
    validate_nct_id,
)
from app.registry.normalize import normalize_study  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "registry"
OBSERVED_AT = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def test_nct_validation_is_strict() -> None:
    assert validate_nct_id("NCT12345678") == "NCT12345678"
    for invalid in (
        "nct12345678",
        "NCT1234567",
        "NCT123456789",
        " NCT12345678",
        "NCT12345678 ",
        "https://clinicaltrials.gov/study/NCT12345678",
        "",
    ):
        try:
            validate_nct_id(invalid)
        except InvalidNCTId:
            pass
        else:
            raise AssertionError(f"{invalid!r} should have been rejected")


def test_normalization_is_allowlisted_and_tracks_missing_fields() -> None:
    record = normalize_study(_fixture("target.json"), retrieved_at=OBSERVED_AT)
    assert record.nct_id == "NCT00000001"
    assert record.status == "RECRUITING"
    assert record.phase == ["PHASE2"]
    assert record.intervention_types == ["DRUG"]
    assert record.source_url == "https://clinicaltrials.gov/study/NCT00000001"
    assert record.retrieved_at == OBSERVED_AT

    serialized = json.dumps(record.model_dump(), default=str)
    for forbidden in (
        "private-contact@example.org",
        "+1-555-0100",
        "Private Contact",
        "Named Investigator",
        "Named Responsible Person",
    ):
        assert forbidden not in serialized

    sparse = normalize_study(_fixture("missing_fields.json"), retrieved_at=OBSERVED_AT)
    assert {
        "title",
        "phases",
        "conditions",
        "intervention_types",
        "study_type",
        "stop_reason",
    }.issubset(set(sparse.missing_fields))


def test_single_fetch_requests_only_allowlisted_fields() -> None:
    payload = _fixture("target.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/studies/NCT00000001"
        fields = request.url.params["fields"]
        assert "NCTId" in fields
        for forbidden in (
            "CentralContact",
            "OverallOfficial",
            "LocationFacility",
            "ResponsibleParty",
        ):
            assert forbidden not in fields
        return httpx.Response(200, json=payload)

    async def exercise() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://clinicaltrials.gov",
        ) as http_client:
            client = ClinicalTrialsClient(
                http_client=http_client,
                clock=lambda: OBSERVED_AT,
            )
            record = await client.fetch_trial("NCT00000001")
            assert record.nct_id == "NCT00000001"

    asyncio.run(exercise())


def test_invalid_id_stops_before_network_and_404_is_specific() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(404, json={})

    async def exercise() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://clinicaltrials.gov",
        ) as http_client:
            client = ClinicalTrialsClient(http_client=http_client)
            try:
                await client.fetch_study_payload("bad")
            except InvalidNCTId:
                pass
            else:
                raise AssertionError("invalid ID should fail")
            assert request_count == 0

            try:
                await client.fetch_study_payload("NCT99999999")
            except RegistryNotFound:
                pass
            else:
                raise AssertionError("404 should raise RegistryNotFound")
            assert request_count == 1

    asyncio.run(exercise())


def test_pagination_reports_complete_and_capped_retrieval() -> None:
    first_page = _fixture("cohort_page_1.json")
    second_page = _fixture("cohort_page_2.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query.cond"] == "Glioblastoma"
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=second_page if token else first_page)

    async def exercise() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://clinicaltrials.gov",
        ) as http_client:
            complete_client = ClinicalTrialsClient(
                http_client=http_client,
                page_size=3,
                max_records=10,
                clock=lambda: OBSERVED_AT,
            )
            complete = await complete_client.search_studies(condition="Glioblastoma")
            assert complete.pagination_complete is True
            assert complete.records_retrieved == 6
            assert complete.pages_retrieved == 2
            assert complete.next_page_token is None

            capped_client = ClinicalTrialsClient(
                http_client=http_client,
                page_size=3,
                max_records=3,
                clock=lambda: OBSERVED_AT,
            )
            capped = await capped_client.search_studies(condition="Glioblastoma")
            assert capped.pagination_complete is False
            assert capped.records_retrieved == 3
            assert capped.next_page_token == "page-2"

    asyncio.run(exercise())
