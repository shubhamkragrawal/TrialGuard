"""ClinicalTrials.gov retrieval and deterministic cohort tools."""

from .client import (
    ALLOWLISTED_API_FIELDS,
    ClinicalTrialsClient,
    InvalidNCTId,
    RegistryError,
    RegistryNotFound,
    RegistryResponseError,
    RegistrySearchResult,
    validate_nct_id,
)
from .cohort import (
    CohortFilters,
    RetrievedCohort,
    build_cohort,
    cohort_numeric_facts,
    derive_cohort_filters,
    matches_cohort,
    retrieve_cohort,
)
from .normalize import normalize_study
from .rank import rank_precedents, similarity_features

__all__ = [
    "ALLOWLISTED_API_FIELDS",
    "ClinicalTrialsClient",
    "CohortFilters",
    "InvalidNCTId",
    "RegistryError",
    "RegistryNotFound",
    "RegistryResponseError",
    "RegistrySearchResult",
    "RetrievedCohort",
    "build_cohort",
    "cohort_numeric_facts",
    "derive_cohort_filters",
    "matches_cohort",
    "normalize_study",
    "rank_precedents",
    "retrieve_cohort",
    "similarity_features",
    "validate_nct_id",
]
