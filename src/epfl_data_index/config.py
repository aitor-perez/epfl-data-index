import os


OPTIONAL_ENV_DEFAULTS = {
    "EDI_OPENSEARCH_EMBEDDING_MODEL_ID": "77D-56ABnEX0QP_uqWw7",
    "EDI_OPENSEARCH_INDEX_NAME": "shared_test_260928",
}


class _Config:
    def __getitem__(self, key):
        try:
            return os.environ[key]
        except KeyError:
            if key in OPTIONAL_ENV_DEFAULTS:
                return OPTIONAL_ENV_DEFAULTS[key]
            raise KeyError(f"Missing required environment variable: {key}") from None


CONFIG = _Config()
