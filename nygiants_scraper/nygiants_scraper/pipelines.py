# nygiants_scraper/pipelines.py
# ------------------------------
# Writes posts and comments to separate JSONL files.
# Handles deduplication so re-runs don't create duplicate records.

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class JsonlWriterPipeline:
    """
    Routes RedditPostItem    -> data/posts.jsonl
            RedditCommentItem -> data/comments.jsonl
    """

    def open_spider(self, posts_path="data/posts.jsonl", comments_path="data/comments.jsonl"):
        posts_path    = Path(posts_path)
        comments_path = Path(comments_path)

        posts_path.parent.mkdir(parents=True, exist_ok=True)
        comments_path.parent.mkdir(parents=True, exist_ok=True)

        # Append mode so re-runs extend the corpus rather than overwrite
        self.posts_file    = posts_path.open("a", encoding="utf-8")
        self.comments_file = comments_path.open("a", encoding="utf-8")

        # Load existing IDs to deduplicate across runs
        self.seen_post_ids    = self._load_existing_ids(posts_path)
        self.seen_comment_ids = self._load_existing_ids(comments_path)

        self.posts_written      = 0
        self.comments_written   = 0
        self.duplicates_skipped = 0

        logger.info(
            f"Pipeline opened. Existing posts: {len(self.seen_post_ids)}, "
            f"existing comments: {len(self.seen_comment_ids)}"
        )

    def close_spider(self):
        self.posts_file.close()
        self.comments_file.close()

        logger.info(
            f"Pipeline closed. Written — posts: {self.posts_written}, "
            f"comments: {self.comments_written}. "
            f"Duplicates skipped: {self.duplicates_skipped}"
        )

    def process_item(self, item):
        item_type = item.get("item_type")

        if item_type == "post":
            post_id = item.get("id")
            if post_id in self.seen_post_ids:
                self.duplicates_skipped += 1
                return item
            self.seen_post_ids.add(post_id)
            self.posts_file.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
            self.posts_written += 1

        elif item_type == "comment":
            comment_id = item.get("id")
            if comment_id in self.seen_comment_ids:
                self.duplicates_skipped += 1
                return item
            self.seen_comment_ids.add(comment_id)
            self.comments_file.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
            self.comments_written += 1

        else:
            logger.warning(f"Unknown item type: {item_type} — skipping")

        return item

    @staticmethod
    def _load_existing_ids(path: Path) -> set:
        """Read existing JSONL and return set of all 'id' values."""
        ids = set()
        if not path.exists():
            return ids
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if "id" in record:
                        ids.add(record["id"])
                except json.JSONDecodeError:
                    continue
        return ids
