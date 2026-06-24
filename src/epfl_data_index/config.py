import os


class _Config:
    def __getitem__(self, key):
        try:
            return os.environ[key]
        except KeyError:
            raise KeyError(f"Missing required environment variable: {key}") from None


CONFIG = _Config()
