"""Async, bounded ClinicalTrials.gov API v2 client."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx

NCT_ID_PATTERN = re.compile(r"^NCT\d{8}$")
DEFAULT_BASE_URL = "https://clinicaltrials.gov"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_RECORDS = 500
DEFAULT_MAX_PAGES = 20

# These API v2 field names map only to the normalized public-data allowlist.
# In particular, no contact, investigator, location, or responsible-party
# fields are requested.
ALLOWLISTED_API_FIELDS = (
    "NCTId",
    "BriefTitle",
    "OfficialTitle",
    "OverallStatus",
    "WhyStopped",
    "StartDate",
    "CompletionDate",
    "StudyType",
    "Phase",
    "Condition",
    "InterventionType",
    "DesignAllocation",
    "DesignInterventionModel",
    "DesignPrimaryPurpose",
    "DesignMasking",
    "EnrollmentCount",
    "EnrollmentType",
)


class RegistryError(RuntimeError):
    """Base exception for registry retrieval failures."""


class InvalidNCTId(ValueError):
    """Raised before network access when an NCT ID is malformed."""


class RegistryNotFound(RegistryError):
    """Raised when ClinicalTrials.gov has no matching study."""


class RegistryResponseError(RegistryError):
    """Raised for a failed or malformed registry response."""


@dataclass(frozen=True)
class RegistrySearchResult:
    studies: tuple[Mapping[str, Any], ...]
    pagination_complete: bool
    pages_retrieved: int
    records_retrieved: int
    total_count: int | None
    retrieved_at: datetime
    query_condition: str
    next_page_token: str | None = None


def validate_nct_id(value: str) -> str:
    """Validate without trimming or case conversion to keep input strict."""

    if not isinstance(value, str) or NCT_ID_PATTERN.fullmatch(value) is None:
        raise InvalidNCTId("NCT ID must match ^NCT\\d{8}$")
    return value


class ClinicalTrialsClient:
    """Read-only API v2 client with explicit pagination and result caps."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int = DEFAULT_MAX_RECORDS,
        max_pages: int = DEFAULT_MAX_PAGES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if max_records < 1 or max_pages < 1:
            raise ValueError("max_records and max_pages must be positive")

        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            headers={"User-Agent": "TrialGuard/1.0"},
        )
        self._page_size = page_size
        self._max_records = max_records
        self._max_pages = max_pages
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def __aenter__(self) -> "ClinicalTrialsClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_study_payload(self, nct_id: str) -> Mapping[str, Any]:
        """Fetch one allowlisted study payload after strict local validation."""

        validated_id = validate_nct_id(nct_id)
        response = await self._request(
            "GET",
            f"/api/v2/studies/{validated_id}",
            params={
                "format": "json",
                "fields": ",".join(ALLOWLISTED_API_FIELDS),
            },
        )
        if response.status_code == 404:
            raise RegistryNotFound(f"No registry study found for {validated_id}")
        return self._json_mapping(response)

    async def fetch_trial(self, nct_id: str) -> Any:
        """Fetch and normalize one study into the shared ``TrialRecord``."""

        from .normalize import normalize_study

        payload = await self.fetch_study_payload(nct_id)
        return normalize_study(payload, retrieved_at=self._utc_now())

    async def search_studies(
        self,
        *,
        condition: str,
        max_records: int | None = None,
    ) -> RegistrySearchResult:
        """Retrieve a condition-bounded set and report exact completeness.

        A result is complete only when the API supplies no next-page token and
        its optional total count is consistent with the received records.
        Hitting either local bound returns a useful but explicitly incomplete
        result.
        """

        query_condition = " ".join(condition.split())
        if not query_condition:
            raise ValueError("condition must be non-empty")
        record_limit = self._max_records if max_records is None else max_records
        if record_limit < 1:
            raise ValueError("max_records must be positive")

        studies: list[Mapping[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        total_count: int | None = None
        pages_retrieved = 0
        pagination_complete = False

        while pages_retrieved < self._max_pages and len(studies) < record_limit:
            remaining = record_limit - len(studies)
            params: dict[str, Any] = {
                "format": "json",
                "query.cond": query_condition,
                "fields": ",".join(ALLOWLISTED_API_FIELDS),
                "countTotal": "true",
                "pageSize": min(self._page_size, remaining),
            }
            if page_token:
                params["pageToken"] = page_token

            response = await self._request("GET", "/api/v2/studies", params=params)
            payload = self._json_mapping(response)
            page_studies = payload.get("studies", [])
            if not isinstance(page_studies, list) or not all(
                isinstance(study, Mapping) for study in page_studies
            ):
                raise RegistryResponseError("Registry response has invalid studies")

            studies.extend(page_studies[:remaining])
            pages_retrieved += 1
            total_count = _optional_nonnegative_int(payload.get("totalCount"), total_count)
            next_token_value = payload.get("nextPageToken")
            next_token = (
                str(next_token_value) if next_token_value not in (None, "") else None
            )

            if next_token is None:
                pagination_complete = total_count is None or len(studies) >= total_count
                page_token = None
                break
            if next_token in seen_tokens:
                page_token = next_token
                break
            seen_tokens.add(next_token)
            page_token = next_token

        if page_token is not None:
            pagination_complete = False

        return RegistrySearchResult(
            studies=tuple(studies),
            pagination_complete=pagination_complete,
            pages_retrieved=pages_retrieved,
            records_retrieved=len(studies),
            total_count=total_count,
            retrieved_at=self._utc_now(),
            query_condition=query_condition,
            next_page_token=page_token,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any],
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, path, params=params)
        except httpx.TimeoutException as exc:
            raise RegistryResponseError("Registry request timed out") from exc
        except httpx.HTTPError as exc:
            raise RegistryResponseError("Registry request failed") from exc

        if response.status_code >= 400 and response.status_code != 404:
            # Do not copy bodies into errors or logs; they are unnecessary here.
            raise RegistryResponseError(
                f"Registry returned HTTP {response.status_code}"
            )
        return response

    @staticmethod
    def _json_mapping(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RegistryResponseError("Registry returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise RegistryResponseError("Registry returned a non-object JSON value")
        return payload

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _optional_nonnegative_int(value: Any, fallback: int | None) -> int | None:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value >= 0:
        return value
    return fallback
