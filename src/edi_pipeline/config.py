"""Pipeline settings: API endpoints, page sizes, and HTTP behaviour.

Run parameters (alias name, date ranges, ...) come from environment
variables / CLI flags, not from this module.
"""
import os

INFOSCIENCE_BASE_URL = "https://infoscience.epfl.ch/server/api"
# Optional bearer token; anonymous access covers public metadata already.
INFOSCIENCE_TOKEN = os.getenv("INFOSCIENCE_TOKEN")
OPENALEX_BASE_URL = "https://api.openalex.org"
ORCID_INTEGRATION_URL = "https://orcid-integration.epfl.ch/export/"
EPFL_SEARCH_API_URL = "https://search-api.epfl.ch/api/unit"

# Infoscience search returns at most 100 results per page.
INFOSCIENCE_PAGE_SIZE = 100
# OpenAlex OR-filters accept at most 100 values per request.
OPENALEX_CHUNK_SIZE = 100
OPENALEX_PER_PAGE = 100

REQUEST_TIMEOUT = 60
POLITE_DELAY_SECONDS = 0.15
WAIT_ON_RETRY = (2, 10, 30, 60)  # seconds between retries

# Free API key from https://openalex.org/settings/api. Without it, requests
# share the small per-IP daily budget.
OPENALEX_API_KEY = os.getenv("EDI_PIPELINE_OPENALEX_API_KEY") or os.getenv("API_KEY_OPENALEX")

# Publication types fetched from OpenAlex (profdb parity).
OPENALEX_TYPES = "article|book|book-chapter"
