# nygiants_scraper/spiders/nygiants_spider.py
# --------------------------------------------
# Scrapy spider that ingests r/NYGiants posts and full comment trees
# via Reddit's public .json endpoints.
#
# Flow:
#   1. Start at /r/NYGiants/new/.json (paginated via `after` token)
#   2. For each post listing → yield RedditPostItem
#   3. Follow permalink + .json → parse full comment tree recursively
#   4. Yield RedditCommentItem for each quality comment
#
# Usage:
#   scrapy crawl nygiants
#   scrapy crawl nygiants -s POST_LIMIT=50
#   scrapy crawl nygiants -s FLAIR_FILTER="Game Thread"
#   scrapy crawl nygiants -s POST_LIMIT=200 -s SORT=top -s TIME_FILTER=year
 
import re
import logging 
from datetime import datetime, timezone
from nygiants_scraper.items import RedditPostItem, RedditCommentItem

import scrapy

logger = logging.getLogger(__name__)

MIN_COMMENT_SCORE   = 2     # Drop net-downvoted noise TODO: heavily downvoted posts contain info too...
MIN_COMMENT_CHARS   = 40    # Drop one-liners ("lol", "this", "LFG")
MIN_POST_SCORE      = 5     # Ignore very low-traction posts
MAX_COMMENT_DEPTH   = 8     # Cap recursion depth

# Reddit paginates at 25 posts per page; 100 is the max per request
POSTS_PER_PAGE = 100

DELETED_BODIES  = {"[deleted]", "[removed]", ""}
BOT_AUTHORS     = {
    "AutoModerator", "reddit", "BotDefense", "RepostSleuthBot",
    "CommonMisspellingBot", "sneakpeek_bot", "ModeratorBot",
}


class NYGiantsSpider(scrapy.Spider):
    name = "nygiants"
    allowed_domains = ["reddit.com","www.reddit.com"]
    
    # Headers that make Reddit's JSON endpoint respond reliably
    REDDIT_HEADERS = {
        "Accept":           "application/json",
        "Accept-Language":  "en-US,en;q=0.9",
    }
    
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        
        # Run time setting (overridable via -s KEY=value on CLI)
        self.post_limit     = int(getattr(self,"POST_LIMIT",200))
        self.flair_filter   = getattr(self,"FLAIR_FILTER",None)
        self.sort           = getattr(self,"SORT", "new")
        self.time_filter    = getattr(self,"TIME_FILTER","all")
        
        self.posts_fetched = 0
        
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Entry Point
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    async def start(self):
        print(f"DEBUG start fired — sort={self.sort}, limit={self.post_limit}")
        url = self._listing_url(sort=self.sort, after=None)
        print(f"DEBUG first URL: {url}")
        logger.info(f"Starting crawl - sort={self.sort}, limit={self.post_limit}, \
                    flair={self.flair_filter or 'all'}")
        yield scrapy.Request(
            url,
            headers=self.REDDIT_HEADERS,
            callback=self.parse_listing,
            meta={"after": None},
        )
    
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Stage 1: Parse the /new/.json listing page
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    def parse_listing(self,response):
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse listing JSON: {e}")
            return
        
        listing = data.get("data", {})
        posts   = listing.get("children", [])
        after   = listing.get("after")  # pagination token TODO: Figure out what is a pagination token
        
        logger.info(f"Listing page: {len(posts)} posts, after={after}")
        
        for post_wrapper in posts:
            if self.posts_fetched >= self.post_limit: # is this a self imposed limit???
                logger.info(f"Reached post limit ({self.post_limit}). Stopping")
                return
            
            post_data = post_wrapper.get("data", {})
            
            # Apply quality and flair filters at listing level
            if not self._post_passes_filters(post_data):
                continue
            
            self.posts_fetched += 1
            
            # Yield the post item immediately - don't wait for comments
            # as soon as post item is available, pause the spider and pass the object to Scrapy Engine to handle HTTP request
            yield self._build_post_item(post_data)
            
            # Follow into the post's comment tree
            permalink = post_data.get("permalink", "")
            comment_url = f"https://www.reddit.com{permalink}.json?limit=500&depth={MAX_COMMENT_DEPTH}"
            yield scrapy.Request(
                comment_url,
                headers=self.REDDIT_HEADERS,
                callback=self.parse_comments,
                meta={
                    "post_id":      post_data.get("id"),
                    "post_title":   post_data.get("title", ""),
                    "post_flair":   post_data.get("link_flair_text") or None,
                    "post_score":   post_data.get("score",0)
                },
            )
                
    
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Stage 2: Parse a post's comment tree
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    def parse_comments(self, response):
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to parse comment JSON: {e} - response.url")
            return
        
        # Reddit returns a 2-element array: [post_listing,comment_listing]
        if not isinstance(data,list) or len(data) < 2:
            logger.warning(f"Unexpected comment JSON structure at {response.url}")
            return
        
        comment_listing = data[1].get("data",{}).get("children",[])
        
        post_meta = {
            "post_id":      response.meta["post_id"],
            "post_title":   response.meta["post_title"],
            "post_flair":   response.meta["post_flair"],
            "post_score":   response.meta["post_score"],
        }    
        
        comment_count = 0
        for item in self._traverse_comments(comment_listing, post_meta, depth=0):
            comment_count += 1
            yield item
            
        logger.info(
            f"Post {post_meta['post_id']}: {comment_count} quality comments extracted"
        )
    
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Comment Tree traversal (recursive)
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    
    def _traverse_comments(self, comment_list, post_meta, depth):
        '''
        Recursively walk the comment tree.
        Yields RedditCommentItem for each comment that passes quality filters.
        Always recurses into replies even wehn the parent comment is filtered - 
        a good reply can have a bad parent.
        '''
        for wrapper in comment_list:
            kind = wrapper.get("kind")
            
            # "more" objects are unexpanded comment stubs
            # "t1" is ??? TODO: Figure out
            if kind == "more" or kind != "t1":
                continue
            
            comment = wrapper.get("data",{})
            passes = self._comment_passes_filters(comment,depth)
            
            if passes: 
                yield self._build_comment_item(comment,post_meta,depth)
                
            # Always recurse regardless of whether parent passsed filters
            replies = comment.get("replies")
            if replies and isinstance(replies,dict):
                children = replies.get("data",{}).get("children",[])
                if children and depth < MAX_COMMENT_DEPTH:
                    yield from self._traverse_comments(children, post_meta,depth+1)
            
        
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Item builders
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    
    def _build_post_item(self,d:dict) -> RedditPostItem:
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

    
    def _build_comment_item(self,d:dict,post_meta:dict,depth:int) -> RedditCommentItem:
        post_id   = post_meta["post_id"]
        comment_id = d.get("id", "")
        permalink = (
            f"https://www.reddit.com/r/NYGiants/comments/{post_id}/ \
            comment/{comment_id}/"
        )
        return RedditCommentItem(
            id            = comment_id,
            post_id       = post_id,
            parent_id     = d.get("parent_id", ""),   # e.g. "t3_abc123" or "t1_xyz789"
            permalink     = permalink,
            body          = self._clean_text(d.get("body", "")),
            post_title    = post_meta["post_title"],
            post_flair    = post_meta["post_flair"],
            post_score    = post_meta["post_score"],
            score         = d.get("score", 0),
            author        = self._safe_author(d.get("author")),
            distinguished = d.get("distinguished"),   # None | "moderator" | "admin"
            depth         = depth,
            created_utc   = self._ts_to_date(d.get("created_utc", 0)),
            created_ts    = int(d.get("created_utc", 0)),
            item_type     = "comment",
        )

    
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Quality Filters
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    
    def _post_passes_filters(self,d:dict) -> bool:
        is_low_traction     = d.get("score",0) < MIN_POST_SCORE
        is_wrong_flair      = self.flair_filter and d.get("link_flair_text") != self.flair_filter
        
        # Skip stickied mod posts (rules, weekly threads, etc.)
        is_stickied         = d.get("stickied") #TODO: don't want to remove weekly or daily threads though
        
        if is_low_traction or is_wrong_flair or is_stickied:
            return False

        return True
    
    def _comment_passes_filters(self,d:dict,depth:int) -> bool:
        author = str(d.get("author") or "")
        body = (d.get("body") or "").strip()
        
        is_too_deep     = depth > MAX_COMMENT_DEPTH
        is_invalid_auth = not author or author in BOT_AUTHORS 
        is_low_traction = d.get("score",0) < MIN_COMMENT_SCORE 
        is_too_short    = len(body) < MIN_COMMENT_CHARS
        is_from_mod     = d.get("distinguished") == "moderator"
        
        if is_too_deep or is_invalid_auth or is_low_traction or is_too_short or is_from_mod:
            return False
        
        return True
        
    
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    ## Helpers
    ##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    def _listing_url(self,sort:str="new",after:str|None=None)-> str:
        base = f"https://www.reddit.com/r/NYGiants/{sort}/.json?limit={POSTS_PER_PAGE}"
        if self.time_filter and sort in ("top","controversial"):
            base += f"&t={self.time_filter}"
        if after:
            base += f"&after={after}"
        return base

    @staticmethod
    def _ts_to_date(ts) -> str:
        """Convert Unix timestamp to YYYY-MM-DD string."""
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
        """
        Light cleaning of Reddit markdown:
        - Strip excessive whitespace
        - Remove common Reddit markdown artifacts
        - Preserve paragraph breaks (important for chunking)
        """
        if not text:
            return ""
        # Collapse excessive blank lines (keep max 2 newlines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip leading/trailing whitespace
        text = text.strip()
        return text

    
    
if __name__ == "__main__":
    spida = NYGiantsSpider()    
    results = spida.start_requests()    
    print(results)
    