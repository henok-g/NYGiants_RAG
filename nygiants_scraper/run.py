# run.py
# ------
# Entry point for the NYGiants scraper.
#
# Usage:
#   python run.py
#   python run.py --post-limit 50
#   python run.py --sort top --time-filter year
#   python run.py --flair-filter "Game Thread"

import argparse
import logging
import os

from dotenv import load_dotenv

from nygiants_scraper.scraper import NYGiantsScraper
from nygiants_scraper.pipelines import JsonlWriterPipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

parser = argparse.ArgumentParser(description="Scrape r/NYGiants posts and comments")
parser.add_argument("--post-limit",   type=int, default=200)
parser.add_argument("--sort",         default="new", choices=["new", "hot", "top", "controversial"])
parser.add_argument("--flair-filter", default=None)
parser.add_argument("--time-filter",  default="all", choices=["hour", "day", "week", "month", "year", "all"])
parser.add_argument("--after",         default=None, help="Reddit pagination token to resume from")
parser.add_argument("--posts-path",    default="data/posts.jsonl")
parser.add_argument("--comments-path", default="data/comments.jsonl")
args = parser.parse_args()

pipeline = JsonlWriterPipeline()
pipeline.open_spider(posts_path=args.posts_path, comments_path=args.comments_path)

cookies = {
    "reddit_session": os.environ["REDDIT_SESSION"],
    "token_v2":       os.environ["REDDIT_TOKEN_V2"],
}

scraper = NYGiantsScraper(
    post_limit=args.post_limit,
    flair_filter=args.flair_filter,
    sort=args.sort,
    time_filter=args.time_filter,
    cookies=cookies,
    after=args.after,
)

try:
    scraper.run(pipeline)
finally:
    pipeline.close_spider()
