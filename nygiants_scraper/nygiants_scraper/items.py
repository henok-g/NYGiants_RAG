# nygiants_scraper/items.py
# -------------------------
# Data contracts for posts and comments.

from typing import Optional, TypedDict


class RedditPostItem(TypedDict):
    # --- Identity ---
    id:              str    # Reddit post ID (e.g. "abc123")
    permalink:       str    # Full URL path for citation

    # --- Content ---
    title:           str    # Post headline
    selftext:        str    # Post body text (empty for link posts)
    url:             str    # External URL if link post, else permalink

    # --- Taxonomy ---
    subreddit:       str    # Always "NYGiants" but store for reusability
    link_flair_text: str    # e.g. "Game Thread", "Discussion", "Injury"

    # --- Engagement ---
    score:           int    # Net upvotes
    upvote_ratio:    float  # e.g. 0.94
    num_comments:    int    # Total comment count

    # --- Attribution ---
    author:          str    # u/username

    # --- Temporal ---
    created_utc:     str    # ISO date string: "YYYY-MM-DD"
    created_ts:      int    # Raw unix timestamp (keep for sorting)

    # --- Internal ---
    item_type:       str    # Always "post" — used by pipeline router


class RedditCommentItem(TypedDict):
    # --- Identity ---
    id:            str           # Comment ID
    post_id:       str           # Parent post ID
    parent_id:     str           # Direct parent — t1_xxx (comment) or t3_xxx (post)
    permalink:     str           # Full URL with comment anchor for citation

    # --- Content ---
    body:          str           # Comment text

    # --- Post context (denormalised for easier chunking downstream) ---
    post_title:    str
    post_flair:    Optional[str]
    post_score:    int

    # --- Engagement ---
    score:         int           # Comment net upvotes

    # --- Attribution ---
    author:        str           # u/username
    distinguished: Optional[str]  # None | "moderator" | "admin"

    # --- Structure ---
    depth:         int           # Nesting depth (0 = top-level)

    # --- Temporal ---
    created_utc:   str           # ISO date string: "YYYY-MM-DD"
    created_ts:    int           # Raw unix timestamp

    # --- Internal ---
    item_type:     str           # Always "comment" — used by pipeline router
