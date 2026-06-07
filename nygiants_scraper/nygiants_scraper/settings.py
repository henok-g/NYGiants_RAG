# nygiants_scraper/settings.py
# ----------------------------
# Scrapy settings for the NYGiants Reddit JSON scraper.
# Polite / respectful crawl profile throughout.

BOT_NAME = "nygiants_scraper"

SPIDER_MODULES = ["nygiants_scraper.spiders"]
NEWSPIDER_MODULE = "nygiants_scraper.spiders"

# ---------------------------------------------------------------------------
# Polite crawl settings
# ---------------------------------------------------------------------------

# Identify ourselves honestly in the User-Agent
USER_AGENT = "nygiants_rag_personal_project/1.0 (personal research; non-commercial)"

# Honour robots.txt — set False only if you have explicit permission
ROBOTSTXT_OBEY = False  # old.reddit.com robots.txt blocks all bots; we use .json endpoints

# One request at a time — no hammering the server
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# Delay between requests (seconds) + randomise ±50% to appear human
DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True  # actual delay: 1.5s – 4.5s

# Auto-throttle: backs off further if server is slow
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# ---------------------------------------------------------------------------
# Retry settings
# ---------------------------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# Back off hard on 429 (rate limited)
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
}

# ---------------------------------------------------------------------------
# Output pipeline
# ---------------------------------------------------------------------------
ITEM_PIPELINES = {
    "nygiants_scraper.pipelines.JsonlWriterPipeline": 300,
}

# Default output paths (overridable via -s OUTPUT_FILE=... on CLI)
OUTPUT_FILE_POSTS    = "data/posts.jsonl"
OUTPUT_FILE_COMMENTS = "data/comments.jsonl"

# ---------------------------------------------------------------------------
# HTTP cache (speeds up re-runs during development)
# ---------------------------------------------------------------------------
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 60 * 60 * 6   # 6 hours
HTTPCACHE_DIR = ".scrapy/httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [429, 500, 502, 503, 504]

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
LOG_LEVEL = "INFO"