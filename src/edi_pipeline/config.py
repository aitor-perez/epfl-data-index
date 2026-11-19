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
# OpenAlex list endpoints allow up to 200 results per page.
OPENALEX_PER_PAGE = 200
# EPFL in OpenAlex, resolved from its ROR (https://ror.org/02s376052).
EPFL_OPENALEX_ID = "I5124864"

REQUEST_TIMEOUT = 60
POLITE_DELAY_SECONDS = 0.15
# Seconds between retries. Long tail on purpose: nothing is cached, so a bulk
# download that gives up on a rate limit loses everything fetched so far.
WAIT_ON_RETRY = (2, 10, 30, 60, 120, 300)
# A refusal's own `Retry-After` wins over WAIT_ON_RETRY: capped, plus a margin.
MAX_RETRY_AFTER_SECONDS = 3600
RETRY_AFTER_MARGIN_SECONDS = 5

# Free API key from https://openalex.org/settings/api. Without it, OpenAlex
# refuses to page past the first results. OPENALEX_API_KEY is the name to
# use; the other two are older names, still read.
OPENALEX_API_KEY = (
    os.getenv("OPENALEX_API_KEY")
    or os.getenv("EDI_PIPELINE_OPENALEX_API_KEY")
    or os.getenv("API_KEY_OPENALEX")
)

# LLM judge of the author disambiguation: EPFL's RCP inference service, an
# OpenAI-compatible endpoint. Only the endpoint and its key are environment
# settings, named after the service. No base URL means no judge.
RCP_BASE_URL = os.getenv("RCP_BASE_URL")
RCP_API_KEY = os.getenv("RCP_API_KEY")
# The judge's model and its sampling preset go together and are defined here,
# not in the environment: to try another model, change both. On RCP (vLLM),
# reasoning is switched off server-side through chat_template_kwargs.
JUDGE_MODEL = "Qwen/Qwen3.6-35B-A3B"
JUDGE_REQUEST_OPTIONS = {
    "temperature": 0.7,
    "top_p": 0.8,
    "presence_penalty": 1.5,
    "extra_body": {
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": False},
    },
}

# Publication types fetched from OpenAlex (profdb parity).
OPENALEX_TYPES = "article|book|book-chapter"

# Yearly download cache (edi_pipeline/download.py). Every year, the current
# one included, is kept on disk and downloaded again once older than
# CACHE_MAX_AGE_DAYS. `data/` is git-ignored.
CACHE_DIR = os.getenv("EDI_PIPELINE_CACHE_DIR", "data/cache")
CACHE_MAX_AGE_DAYS = 30
