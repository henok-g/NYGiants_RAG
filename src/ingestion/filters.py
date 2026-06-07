"""
src/ingestion/filters.py
------------------------
Quality filtering for posts and comments before chunking.

Filters are driven entirely by the pipeline.yaml config so thresholds
can be tuned per experiment without touching code.

Usage:
    from src.ingestion.filters import PostFilter, CommentFilter

    post_filter    = PostFilter(config["ingestion"]["filters"])
    comment_filter = CommentFilter(config["ingestion"]["filters"])

    posts    = post_filter.apply(raw_posts)
    comments = comment_filter.apply(raw_comments)
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default filter thresholds (overridden by pipeline.yaml)
# ---------------------------------------------------------------------------

DEFAULT_POST_FILTERS = {
    "min_post_score":    10,
    "exclude_flairs":    ["Meme/Shitpost", "None"],
    "exclude_authors":   ["u/AutoModerator"],
    "min_selftext_chars": 0,       # 0 = allow link posts with no body
}

DEFAULT_COMMENT_FILTERS = {
    "min_comment_score":  2,
    "min_comment_chars":  40,
    "max_depth":          6,
    "exclude_authors":    ["u/AutoModerator"],
    "exclude_bodies":     ["[deleted]", "[removed]", ""],
}

# Authors that are always bots regardless of config
HARDCODED_BOT_AUTHORS = {
    "u/AutoModerator",
    "u/reddit",
    "u/BotDefense",
    "u/RepostSleuthBot",
    "u/CommonMisspellingBot",
    "u/sneakpeek_bot",
    "u/ModeratorBot",
}

# Regex patterns for low-signal comment bodies
LOW_SIGNAL_PATTERNS = [
    r"^\s*this\s*$",              # "this"
    r"^\s*lol\s*$",               # "lol"
    r"^\s*lmao\s*$",              # "lmao"
    r"^\s*😂+\s*$",               # pure emoji
    r"^\s*f\s*$",                 # "F" (pay respects meme)
    r"^\s*\^+\s*$",               # "^^^" (agreement arrows)
    r"^\s*same\s*$",              # "same"
    r"^\s*yep\s*$",               # "yep"
    r"^\s*nope\s*$",              # "nope"
    r"^\s*wow\s*$",               # "wow"
    r"^\s*[+\-]?\d+\s*$",        # pure numbers e.g. "+1", "-1", "100"
]

LOW_SIGNAL_RE = re.compile(
    "|".join(LOW_SIGNAL_PATTERNS),
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Filter result dataclass — makes logging and debugging clean
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    passed:  list
    dropped: dict   # reason -> list of ids

    @property
    def total_dropped(self) -> int:
        return sum(len(v) for v in self.dropped.values())

    def log_summary(self, label: str):
        logger.info(
            f"{label} filter summary: "
            f"{len(self.passed)} passed, "
            f"{self.total_dropped} dropped"
        )
        for reason, items in self.dropped.items():
            if items:
                logger.info(f"  {reason}: {len(items)}")


# ---------------------------------------------------------------------------
# Post filter
# ---------------------------------------------------------------------------

class PostFilter:
    """
    Filters raw post records loaded from posts.jsonl.

    Args:
        config: dict from pipeline.yaml ingestion.filters section
    """

    def __init__(self, config: dict):
        self.min_score       = config.get("min_post_score",     DEFAULT_POST_FILTERS["min_post_score"])
        self.exclude_flairs  = set(config.get("exclude_flairs", DEFAULT_POST_FILTERS["exclude_flairs"]))
        self.exclude_authors = set(config.get("exclude_authors", DEFAULT_POST_FILTERS["exclude_authors"])) | HARDCODED_BOT_AUTHORS
        self.min_selftext    = config.get("min_selftext_chars",  DEFAULT_POST_FILTERS["min_selftext_chars"])

    def apply(self, posts: list[dict]) -> FilterResult:
        """
        Apply all post filters and return a FilterResult.

        Args:
            posts: list of post dicts loaded from posts.jsonl

        Returns:
            FilterResult with passed posts and drop reasons
        """
        passed  = []
        dropped = {
            "low_score":      [],
            "excluded_flair": [],
            "bot_author":     [],
            "short_selftext": [],
        }

        for post in posts:
            post_id = post.get("id", "unknown")

            # Score filter
            if post.get("score", 0) < self.min_score:
                dropped["low_score"].append(post_id)
                continue

            # Flair filter
            flair = post.get("link_flair_text") or "None"
            if flair in self.exclude_flairs:
                dropped["excluded_flair"].append(post_id)
                continue

            # Author filter
            author = post.get("author", "")
            if author in self.exclude_authors:
                dropped["bot_author"].append(post_id)
                continue

            # Selftext length filter (only applies to self posts)
            selftext = post.get("selftext", "") or ""
            if self.min_selftext > 0 and len(selftext.strip()) < self.min_selftext:
                dropped["short_selftext"].append(post_id)
                continue

            passed.append(post)

        result = FilterResult(passed=passed, dropped=dropped)
        result.log_summary("Post")
        return result


# ---------------------------------------------------------------------------
# Comment filter
# ---------------------------------------------------------------------------

class CommentFilter:
    """
    Filters raw comment records loaded from comments.jsonl.

    Args:
        config: dict from pipeline.yaml ingestion.filters section
    """

    def __init__(self, config: dict):
        self.min_score       = config.get("min_comment_score",  DEFAULT_COMMENT_FILTERS["min_comment_score"])
        self.min_chars       = config.get("min_comment_chars",  DEFAULT_COMMENT_FILTERS["min_comment_chars"])
        self.max_depth       = config.get("max_depth",          DEFAULT_COMMENT_FILTERS["max_depth"])
        self.exclude_authors = set(config.get("exclude_authors", DEFAULT_COMMENT_FILTERS["exclude_authors"])) | HARDCODED_BOT_AUTHORS
        self.exclude_bodies  = set(config.get("exclude_bodies",  DEFAULT_COMMENT_FILTERS["exclude_bodies"]))

    def apply(self, comments: list[dict]) -> FilterResult:
        """
        Apply all comment filters and return a FilterResult.

        Args:
            comments: list of comment dicts loaded from comments.jsonl

        Returns:
            FilterResult with passed comments and drop reasons
        """
        passed  = []
        dropped = {
            "low_score":    [],
            "too_short":    [],
            "too_deep":     [],
            "bot_author":   [],
            "deleted_body": [],
            "low_signal":   [],
        }

        for comment in comments:
            comment_id = comment.get("id", "unknown")
            body       = (comment.get("body") or "").strip()

            # Deleted / removed body
            if body in self.exclude_bodies:
                dropped["deleted_body"].append(comment_id)
                continue

            # Author filter
            author = comment.get("author", "")
            if author in self.exclude_authors:
                dropped["bot_author"].append(comment_id)
                continue

            # Score filter
            if comment.get("score", 0) < self.min_score:
                dropped["low_score"].append(comment_id)
                continue

            # Depth filter
            if comment.get("depth", 0) > self.max_depth:
                dropped["too_deep"].append(comment_id)
                continue

            # Minimum character length
            if len(body) < self.min_chars:
                dropped["too_short"].append(comment_id)
                continue

            # Low signal pattern filter ("this", "lol", "+1", pure emoji etc.)
            if LOW_SIGNAL_RE.match(body):
                dropped["low_signal"].append(comment_id)
                continue

            passed.append(comment)

        result = FilterResult(passed=passed, dropped=dropped)
        result.log_summary("Comment")
        return result


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    import json
    records = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping malformed line {i} in {path}: {e}")
    logger.info(f"Loaded {len(records)} records from {path}")
    return records


def load_corpus(config: dict) -> tuple[list[dict], list[dict]]:
    """
    Load and filter posts and comments from JSONL files.

    Returns:
        (filtered_posts, filtered_comments)
    """
    ingestion_cfg = config["ingestion"]
    filter_cfg    = ingestion_cfg["filters"]

    # Load raw records
    raw_posts    = load_jsonl(ingestion_cfg["posts_file"])
    raw_comments = load_jsonl(ingestion_cfg["comments_file"])

    # Apply filters
    post_filter    = PostFilter(filter_cfg)
    comment_filter = CommentFilter(filter_cfg)

    post_result    = post_filter.apply(raw_posts)
    comment_result = comment_filter.apply(raw_comments)

    # Cross-filter: drop comments whose parent post was filtered out
    valid_post_ids = {p["id"] for p in post_result.passed}
    comments_with_valid_posts = [
        c for c in comment_result.passed
        if c.get("post_id") in valid_post_ids
    ]

    orphaned = len(comment_result.passed) - len(comments_with_valid_posts)
    if orphaned:
        logger.info(f"Dropped {orphaned} comments whose parent post was filtered out")

    logger.info(
        f"Corpus ready: "
        f"{len(post_result.passed)} posts, "
        f"{len(comments_with_valid_posts)} comments"
    )

    return post_result.passed, comments_with_valid_posts