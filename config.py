"""Central settings for the Job Search Agent.

Tuned for ~10s responses on Mac CPU (after model warmup).
"""

# Smallest strong-enough free instruct model for on-device speed
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"

# Very short generations — long JSON dumps are too slow on CPU
MAX_NEW_TOKENS = 160

# Soft cap on jobs returned after post-processing
MAX_JOBS = 6

# Default lookback if the user does not specify recency (days)
DEFAULT_POSTED_WITHIN_DAYS = 7

# Fast retrieval limits
SEARCH_RESULTS = 5
PAGES_TO_READ = 2
PAGE_CHAR_LIMIT = 700

# Give up on the LLM and return search hits if it exceeds this
LLM_TIMEOUT_SECONDS = 6
