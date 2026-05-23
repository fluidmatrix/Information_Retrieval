"""
Web Crawler + Inverted Index (Unit 7 Assignment)
================================================
Combines:
  - Unit 7 depth-first web crawler (URL frontier, BeautifulSoup HTML stripping)
  - Indexer Part 2 components (PorterStemmer, Term, flush/index logic, TF-IDF)

Imports from the existing repo modules to avoid code duplication:
    PorterStemmer  ← PorterStemmer.py
    Term           ← Term.py
    flush_block,
    write_index_dat,
    parsetoken,
    STOP_WORDS     ← Code_Indexer_part2.py

Usage:
    python webcrawler_indexer.py
    >>> Enter URL to crawl (must be in the form http://www.domain.com): http://example.com

Output:
    webcrawler.db   – SQLite database (DocumentDictionary, TermDictionary, Posting)
    index.dat       – Human-readable flat-file inverted index
    Runtime statistics printed to console
"""

import os
import re
import time
import sqlite3

# ===========================================================================
# Repo module imports  (OOP / modular design)
# ===========================================================================
# These modules already exist in the repo – no code is duplicated here.
# PorterStemmer.py  → PorterStemmer class
# Term.py           → Term class
# Code_Indexer_part2.py → shared indexing helpers and constants

from PorterStemmer import PorterStemmer
from Term import Term
from Code_Indexer_part2 import (
    STOP_WORDS,        # 75-word stop list
    flush_block,       # persist in-memory dict → SQLite, then clear
    write_index_dat,   # final TF-IDF pass + human-readable index.dat
    parsetoken,        # tokenise one line into the shared `database` dict
    database,          # shared in-memory { stemmed_term → Term() } dict
    tokens,            # module-level counters (accessed via the module)
    terms,
    stop_word_hits,
)
import Code_Indexer_part2 as indexer   # for mutating the module-level counters


# ===========================================================================
# ANSI colour helpers  (keeps all escape codes in one place)
# ===========================================================================
# Usage:  C.RED + "text" + C.RESET
#         C.fmt(C.GREEN, "text")

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[31m"   # errors / warnings
    GREEN  = "\033[32m"   # success / indexed page
    YELLOW = "\033[33m"   # caution / frontier limit
    BLUE   = "\033[34m"   # section headers / prompts
    CYAN   = "\033[36m"   # file output confirmation
    GREY   = "\033[90m"   # queue chatter / per-page detail
    WHITE  = "\033[97m"   # neutral labels

    @staticmethod
    def fmt(color, text):
        return color + text + C.RESET


# ===========================================================================
# URL fetching  (Python 3 / Python 2 compatible shim)
# ===========================================================================

try:
    import urllib.request as _urllib_request
    import urllib.parse   as _urllib_parse

    def url_open(url):
        req = _urllib_request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CourseBot/1.0)"}
        )
        return _urllib_request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")

    def url_parse(url):
        return _urllib_parse.urlparse(url)

except ImportError:                     # Python 2 fallback
    import urllib
    import urllib.parse as _urllib_parse

    def url_open(url):
        return urllib.urlopen(url, timeout=10).read()

    def url_parse(url):
        return _urllib_parse.urlparse(url)


# ===========================================================================
# HTML stripping
# ===========================================================================
# Uses BeautifulSoup when available (pip install beautifulsoup4).
# Falls back to a regex tag-stripper so the script runs without extra deps.

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False


def strip_html(raw_html):
    """Remove all HTML tags and return plain text."""
    if _BS4:
        return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ")
    # Regex fallback
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = re.sub(r'&[a-z]+;', ' ', text)
    return text


# ===========================================================================
# index_page  –  tokenise one page's plain text
# ===========================================================================

def index_page(text, doc_id, cur):
    """Feed each line of a page's plain text through parsetoken (from indexer)."""
    for line in text.splitlines():
        parsetoken(line, doc_id, cur)   # imported from Code_Indexer_part2


# ===========================================================================
# Web Crawler  (DFS / stack-based, depth-first)
# ===========================================================================

SKIP_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.asp',
    '.zip', '.mp3', '.mp4', '.svg', '.ico', '.css', '.js'
}


def crawl(start_url, cur, max_frontier=500):
    """
    Depth-first web crawl starting at start_url.

    - Stack (list.pop) for DFS traversal.
    - crawled set prevents re-visiting URLs.
    - links_in_frontier enforces the 500-URL limit.
    - After each page: text is indexed via parsetoken(), then flush_block()
      keeps memory usage bounded to one page's vocabulary at a time.
    """
    crawled            = set()
    tocrawl            = [start_url]
    links_in_frontier  = 1

    while tocrawl:
        url = tocrawl.pop()

        if url in crawled:
            continue

        # Skip binary / non-text extensions
        ext = os.path.splitext(url.lower().split('?')[0])[1]
        if ext in SKIP_EXTENSIONS:
            crawled.add(url)
            continue

        print(C.GREY + "[%d in queue]  Crawling: " % len(tocrawl) + C.RESET
              + C.WHITE + url + C.RESET)

        # ── Fetch ─────────────────────────────────────────────────────────
        try:
            raw_html = url_open(url)
        except Exception as e:
            print(C.RED + "  ✗ SKIP (fetch error): " + C.RESET
                  + C.GREY + str(e) + C.RESET)
            crawled.add(url)
            continue

        # ── Strip HTML → plain text ───────────────────────────────────────
        text = strip_html(raw_html)

        # ── Index the page ────────────────────────────────────────────────
        indexer.documents += 1
        doc_id = indexer.documents

        cur.execute(
            "INSERT INTO DocumentDictionary VALUES (?, ?)",
            (url, doc_id)
        )
        index_page(text, doc_id, cur)

        # flush_block() is imported from Code_Indexer_part2;
        # it writes the in-memory database dict to SQLite then clears it,
        # keeping peak memory proportional to a single page's vocabulary.
        flush_block(cur)

        print(C.GREEN + "  ✔ Indexed" + C.RESET
              + C.GREY + "  doc_id=%-4d  terms_so_far=%d"
              % (doc_id, indexer.terms) + C.RESET)

        crawled.add(url)

        # ── Harvest outbound links → URL frontier ─────────────────────────
        if links_in_frontier < max_frontier:
            parsed    = url_parse(url)
            base      = parsed.scheme + "://" + parsed.netloc
            raw_links = re.findall(r'''href=["'](.[^"']+)["']''', raw_html, re.I)

            for link in raw_links:
                link = link.strip()
                if not link or link.startswith('#') or link.startswith('mailto:'):
                    continue

                # Normalise relative → absolute URLs
                if link.startswith('//'):
                    link = parsed.scheme + ':' + link
                elif link.startswith('/'):
                    link = base + link
                elif not link.startswith('http'):
                    link = base + '/' + link

                if link not in crawled and links_in_frontier < max_frontier:
                    tocrawl.append(link)
                    links_in_frontier += 1

                if links_in_frontier >= max_frontier:
                    print(C.YELLOW
                          + "  ⚠  URL frontier limit (%d) reached – "
                            "no more links added." % max_frontier
                          + C.RESET)
                    break


# ===========================================================================
# Main
# ===========================================================================

if __name__ == '__main__':

    # ── Prompt for starting URL ───────────────────────────────────────────
    start_url = input(
        C.BLUE + C.BOLD + "Enter URL to crawl" + C.RESET
        + C.BLUE + " (must be in the form http://www.domain.com): " + C.RESET
    ).strip()
    if not start_url.startswith("http"):
        start_url = "http://" + start_url

    # ── Configuration ────────────────────────────────────────────────────
    db_path  = "webcrawler.db"
    dat_path = "index.dat"

    # ── Banner ────────────────────────────────────────────────────────────
    t_start = time.localtime()
    print(C.BLUE + "=" * 46 + C.RESET)
    print(C.BLUE + C.BOLD + "  Web Crawler + Indexer  starting..." + C.RESET)
    print(C.fmt(C.GREY, "  Target  : ") + C.WHITE + start_url + C.RESET)
    print(C.fmt(C.GREY, "  DB      : ") + C.WHITE + db_path   + C.RESET)
    print(C.fmt(C.GREY, "  Index   : ") + C.WHITE + dat_path  + C.RESET)
    print(C.BLUE + "=" * 46 + C.RESET)
    print(C.fmt(C.GREY, "Start Time: %.2d:%.2d"
                % (t_start.tm_hour, t_start.tm_min)))

    # ── Database setup ───────────────────────────────────────────────────
    con = sqlite3.connect(db_path)
    con.isolation_level = None      # autocommit
    cur = con.cursor()

    # Document Dictionary
    cur.execute("DROP TABLE  IF EXISTS DocumentDictionary")
    cur.execute("DROP INDEX  IF EXISTS idxDocumentDictionary")
    cur.execute("CREATE TABLE  IF NOT EXISTS DocumentDictionary "
                "(DocumentName TEXT, DocId INT)")
    cur.execute("CREATE INDEX  IF NOT EXISTS idxDocumentDictionary "
                "ON DocumentDictionary (DocId)")

    # Term Dictionary
    cur.execute("DROP TABLE  IF EXISTS TermDictionary")
    cur.execute("DROP INDEX  IF EXISTS idxTermDictionary")
    cur.execute("CREATE TABLE  IF NOT EXISTS TermDictionary "
                "(Term TEXT, TermId INT)")
    cur.execute("CREATE INDEX  IF NOT EXISTS idxTermDictionary "
                "ON TermDictionary (TermId)")

    # Postings
    cur.execute("DROP TABLE  IF EXISTS Posting")
    cur.execute("DROP INDEX  IF EXISTS idxPosting1")
    cur.execute("DROP INDEX  IF EXISTS idxPosting2")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Posting (
            TermId   INT,
            DocId    INT,
            tfidf    REAL,
            docfreq  INT,
            termfreq INT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idxPosting1 ON Posting (TermId)")
    cur.execute("CREATE INDEX IF NOT EXISTS idxPosting2 ON Posting (DocId)")

    # ── Run the crawler ───────────────────────────────────────────────────
    crawl(start_url, cur, max_frontier=500)

    t_index = time.localtime()
    print(C.GREEN + C.BOLD
          + "Indexing Complete, write to disk: %.2d:%.2d"
            % (t_index.tm_hour, t_index.tm_min)
          + C.RESET)

    # Safety net: flush anything left in memory (normally empty after crawl)
    if indexer.database:
        flush_block(cur)

    # ── Write index.dat  (imported from Code_Indexer_part2) ───────────────
    write_index_dat(dat_path, cur, indexer.documents)

    con.commit()
    con.close()

    # ── Final Statistics ──────────────────────────────────────────────────
    t_end = time.localtime()
    print(C.BLUE + "=" * 46 + C.RESET)
    print(C.BLUE + C.BOLD + "  Crawler Statistics" + C.RESET)
    print(C.BLUE + "=" * 46 + C.RESET)
    print(C.fmt(C.GREY, "  Documents processed   : ")
          + C.WHITE + "%i" % indexer.documents     + C.RESET)
    print(C.fmt(C.GREY, "  Total tokens parsed   : ")
          + C.WHITE + "%i" % indexer.tokens        + C.RESET)
    print(C.fmt(C.GREY, "  Unique terms in index : ")
          + C.WHITE + "%i" % indexer.terms         + C.RESET)
    print(C.fmt(C.GREY, "  Stop word matches     : ")
          + C.WHITE + "%i" % indexer.stop_word_hits + C.RESET)
    print(C.fmt(C.GREY, "  End Time              : ")
          + C.WHITE + "%.2d:%.2d" % (t_end.tm_hour, t_end.tm_min) + C.RESET)
    print(C.BLUE + "=" * 46 + C.RESET)