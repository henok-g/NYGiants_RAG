# nygiants_scraper/scraper.py
# ---------------------------
# Scrapes r/NYGiants posts and full comment trees via Reddit's public .json
# endpoints. Uses curl_cffi to mimic Chrome's TLS fingerprint so Reddit
# doesn't block the requests.
#
# Flow:
#   1. Fetch /r/NYGiants/<sort>/.json (paginated via `after` token)
#   2. For each post → yield RedditPostItem to pipeline
#   3. Fetch permalink + .json → parse full comment tree recursively
#   4. Yield RedditCommentItem for each quality comment to pipeline

import re
import time
import random
import logging
from datetime import datetime, timezone

from curl_cffi import requests as curl_requests

from nygiants_scraper.items import RedditPostItem, RedditCommentItem

logger = logging.getLogger(__name__)

MIN_COMMENT_SCORE = 2
MIN_COMMENT_CHARS = 40
MIN_POST_SCORE    = 5
MAX_COMMENT_DEPTH = 8
POSTS_PER_PAGE    = 100

BOT_AUTHORS = {
    "AutoModerator", "reddit", "BotDefense", "RepostSleuthBot",
    "CommonMisspellingBot", "sneakpeek_bot", "ModeratorBot",
}



class NYGiantsScraper:

    def __init__(
        self,
        post_limit:   int        = 200,
        flair_filter: str | None = None,
        sort:         str        = "new",
        time_filter:  str        = "all",
        delay:        float      = 3.0,
        cookies:      dict | None = None,
        after:        str | None = None,
    ):
        self.post_limit   = post_limit
        self.flair_filter = flair_filter
        self.sort         = sort
        self.time_filter  = time_filter
        self.delay        = delay
        self.cookies      = cookies or {}
        self.after        = after
        self.posts_fetched = 0

    # -------------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------------

    def run(self, pipeline):
        logger.info(
            f"Starting crawl — sort={self.sort}, limit={self.post_limit}, "
            f"flair={self.flair_filter or 'all'}"
        )
        after = self.after
        while self.posts_fetched < self.post_limit:
            url  = self._listing_url(after=after)
            data = self._get_json(url)
            if not data:
                logger.error("Failed to fetch listing page — stopping")
                break

            listing = data.get("data", {})
            posts   = listing.get("children", [])
            after   = listing.get("after")

            logger.info(f"Listing page: {len(posts)} posts, after={after}")

            for post_wrapper in posts:
                if self.posts_fetched >= self.post_limit:
                    logger.info(f"Reached post limit ({self.post_limit})")
                    return
                post_data = post_wrapper.get("data", {})
                if not self._post_passes_filters(post_data):
                    continue
                self.posts_fetched += 1
                pipeline.process_item(self._build_post_item(post_data))
                self._sleep()
                self._fetch_comments(post_data, pipeline)
                self._sleep()

            if not after:
                logger.info("No more pages — crawl complete")
                break
            self._sleep()

        logger.info(f"Crawl finished. Total posts fetched: {self.posts_fetched}")
        if after:
            logger.info(f"Resume token: --after {after}")

    # -------------------------------------------------------------------------
    # Stage 2: Comments
    # -------------------------------------------------------------------------

    def _fetch_comments(self, post_data: dict, pipeline):
        permalink = post_data.get("permalink", "")
        url  = f"https://www.reddit.com{permalink}.json?limit=500&depth={MAX_COMMENT_DEPTH}"
        data = self._get_json(url)
        if not data:
            return
        if not isinstance(data, list) or len(data) < 2:
            logger.warning(f"Unexpected comment structure at {url}")
            return

        comment_listing = data[1].get("data", {}).get("children", [])
        post_meta = {
            "post_id":    post_data.get("id"),
            "post_title": post_data.get("title", ""),
            "post_flair": post_data.get("link_flair_text") or None,
            "post_score": post_data.get("score", 0),
        }

        count = 0
        for item in self._traverse_comments(comment_listing, post_meta, depth=0):
            pipeline.process_item(item)
            count += 1
        logger.info(f"Post {post_meta['post_id']}: {count} quality comments extracted")

    # -------------------------------------------------------------------------
    # Comment tree traversal (recursive)
    # -------------------------------------------------------------------------

    def _traverse_comments(self, comment_list, post_meta, depth):
        """
        Recursively walk the comment tree.
        Yields RedditCommentItem for each comment that passes quality filters.
        Always recurses into replies even when the parent comment is filtered —
        a good reply can have a bad parent.
        """
        for wrapper in comment_list:
            kind = wrapper.get("kind")
            if kind == "more" or kind != "t1":
                continue
            comment = wrapper.get("data", {})
            if self._comment_passes_filters(comment, depth):
                yield self._build_comment_item(comment, post_meta, depth)
            replies = comment.get("replies")
            if replies and isinstance(replies, dict):
                children = replies.get("data", {}).get("children", [])
                if children and depth < MAX_COMMENT_DEPTH:
                    yield from self._traverse_comments(children, post_meta, depth + 1)

    # -------------------------------------------------------------------------
    # HTTP
    # -------------------------------------------------------------------------

    def _get_json(self, url: str, retries: int = 3):
        for attempt in range(retries):
            try:
                resp = curl_requests.get(url, impersonate="firefox135", cookies=self.cookies)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    logger.warning("Rate limited (429) — sleeping 60s")
                    time.sleep(60)
                else:
                    logger.warning(f"HTTP {resp.status_code} for {url} (attempt {attempt + 1})")
                    time.sleep(5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {e}")
                time.sleep(5 * (attempt + 1))
        logger.error(f"Gave up after {retries} attempts: {url}")
        return None

    def _sleep(self):
        time.sleep(self.delay * random.uniform(0.5, 1.5))

    # -------------------------------------------------------------------------
    # Item builders
    # -------------------------------------------------------------------------

    def _build_post_item(self, d: dict) -> RedditPostItem:
        return RedditPostItem(
            id              = d.get("id"),
            permalink       = f"https://www.reddit.com{d.get('permalink', '')}",
            title           = d.get("title", "").strip(),
            selftext        = self._clean_text(d.get("selftext", "")),
            url             = d.get("url", ""),
            subreddit       = d.get("subreddit", "NYGiants"),
            link_flair_text = d.get("link_flair_text") or "None",
            score           = d.get("score", 0),
            upvote_ratio    = d.get("upvote_ratio", 0.0),
            num_comments    = d.get("num_comments", 0),
            author          = self._safe_author(d.get("author")),
            created_utc     = self._ts_to_date(d.get("created_utc", 0)),
            created_ts      = int(d.get("created_utc", 0)),
            item_type       = "post",
        )

    def _build_comment_item(self, d: dict, post_meta: dict, depth: int) -> RedditCommentItem:
        post_id    = post_meta["post_id"]
        comment_id = d.get("id", "")
        permalink  = f"https://www.reddit.com/r/NYGiants/comments/{post_id}/comment/{comment_id}/"
        return RedditCommentItem(
            id            = comment_id,
            post_id       = post_id,
            parent_id     = d.get("parent_id", ""),
            permalink     = permalink,
            body          = self._clean_text(d.get("body", "")),
            post_title    = post_meta["post_title"],
            post_flair    = post_meta["post_flair"],
            post_score    = post_meta["post_score"],
            score         = d.get("score", 0),
            author        = self._safe_author(d.get("author")),
            distinguished = d.get("distinguished"),
            depth         = depth,
            created_utc   = self._ts_to_date(d.get("created_utc", 0)),
            created_ts    = int(d.get("created_utc", 0)),
            item_type     = "comment",
        )

    # -------------------------------------------------------------------------
    # Quality filters
    # -------------------------------------------------------------------------

    def _post_passes_filters(self, d: dict) -> bool:
        if d.get("score", 0) < MIN_POST_SCORE:
            return False
        if self.flair_filter and d.get("link_flair_text") != self.flair_filter:
            return False
        if d.get("stickied"):
            return False
        return True

    def _comment_passes_filters(self, d: dict, depth: int) -> bool:
        author = str(d.get("author") or "")
        body   = (d.get("body") or "").strip()
        if depth > MAX_COMMENT_DEPTH:
            return False
        if not author or author in BOT_AUTHORS:
            return False
        if d.get("score", 0) < MIN_COMMENT_SCORE:
            return False
        if len(body) < MIN_COMMENT_CHARS:
            return False
        if d.get("distinguished") == "moderator":
            return False
        return True

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _listing_url(self, after: str | None = None) -> str:
        base = f"https://www.reddit.com/r/NYGiants/{self.sort}/.json?limit={POSTS_PER_PAGE}"
        if self.time_filter and self.sort in ("top", "controversial"):
            base += f"&t={self.time_filter}"
        if after:
            base += f"&after={after}"
        return base

    @staticmethod
    def _ts_to_date(ts) -> str:
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""

    @staticmethod
    def _safe_author(author) -> str:
        if not author or str(author) in ("[deleted]", "None"):
            return "[deleted]"
        return f"u/{author}"

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
