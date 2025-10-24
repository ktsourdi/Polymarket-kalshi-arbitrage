"""Constants used throughout the application.

This module centralizes magic numbers and configuration values that appear
across multiple modules. This improves maintainability and allows easy
tuning of algorithm parameters.
"""

# Matching algorithm constants
DEFAULT_SIMILARITY_THRESHOLD = 0.72
MAX_TARGETS_PER_SOURCE = 40
DEFAULT_MIN_COSINE = 0.82
MAX_KALSHI_CANDIDATES = 800
TOP_K_PER_POLY = 3

# Embedding processing constants
EMBEDDING_CHUNK_SIZE = 96
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

# API and pagination constants
DEFAULT_MAX_PAGES = 10
DEFAULT_PAGE_LIMIT = 1000
API_TIMEOUT_SECONDS = 15
POLYMARKET_OB_CONCURRENCY = 8

# Progress reporting intervals
PROGRESS_REPORT_INTERVAL = 200  # Report progress every N items
EMBEDDING_PROGRESS_INTERVAL = 50  # Report embedding progress every N items

# Token extraction constants
MIN_TOKEN_LENGTH = 3

# Market filtering constants
POLYMARKET_PAST_DAYS = 30
POLYMARKET_FUTURE_DAYS = 365

# Cursor pagination constants
POLYMARKET_START_CURSOR = "MA=="
POLYMARKET_END_CURSOR = "LTE="

# Display and diagnostic constants
MAX_DISPLAY_CANDIDATES = 20
DIAGNOSTIC_SAMPLE_SIZE = 5


