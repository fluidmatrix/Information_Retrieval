import sys, os, re
import math
import sqlite3
import time
import string
from PorterStemmer import PorterStemmer
from Term import Term

# ==============================================================================
# Stop Words List (75 words)
# ==============================================================================

STOP_WORDS = set([
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "between", "both", "but", "by", "can", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further", "get",
    "got", "had", "has", "have", "having", "he", "her", "here", "him", "his",
    "how", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "no", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "out", "own", "same", "she", "so", "some",
    "such", "than", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "up", "us",
    "very", "was", "we", "were", "what", "when", "which", "while", "who",
    "will", "with", "you", "your"
])

# ==============================================================================
# Global State
# ==============================================================================

# In-memory block: { stemmed_term -> Term() }
# Cleared after every document is fully processed.
database = {}

# Regex: split on non-word characters
chars = re.compile(r'\W+')

# Counters
tokens        = 0   # total raw tokens seen (including all filtered ones)
documents     = 0   # total documents processed
terms         = 0   # unique stemmed terms added to the index
stop_word_hits = 0  # tokens matched against the stop words list

# Memory is flushed to disk after every complete document — no hard term limit needed.
stemmer = PorterStemmer()

# ==============================================================================
# Helpers
# ==============================================================================

def splitchars(line):
    return chars.split(line)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def should_skip(token):
    """Return True if the token should be ignored before stemming."""
    if len(token) == 0:
        return True
    if token[0] in string.punctuation:   # begins with a punctuation character
        return True
    if len(token) <= 2:                   # 2 characters or shorter
        return True
    if is_number(token):                  # pure number
        return True
    return False


# ==============================================================================
# Token Parsing
# ==============================================================================

def parsetoken(line, doc_id, cur):
    """
    Parse one line from a document into stemmed tokens and accumulate them in
    the in-memory `database` dict.

    `cur` is passed in so we can look up whether a term already has a TermId
    in SQLite (from a previous document's flush).  This is the key fix for the
    duplicate-term / DF=1 bug: without the lookup, every document flush would
    mint a fresh TermId for a term it had never seen *in memory*, producing
    duplicate rows and a DF that never exceeded 1.
    """
    global tokens, terms, stop_word_hits

    line = line.replace('\t', ' ').strip()
    parts = splitchars(line)

    for elmt in parts:
        elmt = elmt.replace('\n', '').lower().strip()
        if not elmt:
            continue

        tokens += 1

        # 1. Stop word check — applied to the raw lowercased token
        if elmt in STOP_WORDS:
            stop_word_hits += 1
            continue

        # 2. Structural filters (punctuation-leading, too short, numeric)
        if should_skip(elmt):
            continue

        # 3. Porter Stemming
        stemmed = stemmer.stem(elmt, 0, len(elmt) - 1)

        # 4. Post-stem length guard
        if len(stemmed) <= 2:
            continue

        # 5. Add to in-memory index
        if stemmed not in database:
            # ── Has this term been flushed to SQLite in a previous document? ──
            # If yes, reuse its existing TermId so all postings share one ID.
            # If no,  assign the next available integer and it will be written
            # to TermDictionary on the next flush.
            cur.execute(
                "SELECT TermId FROM TermDictionary WHERE Term = ?", (stemmed,)
            )
            row = cur.fetchone()
            if row:
                tid = row[0]            # reuse the ID already on disk
            else:
                terms += 1
                tid = terms             # brand-new term — claim the next ID

            database[stemmed] = Term()
            database[stemmed].termid = tid
            database[stemmed].docids = {}
            database[stemmed].docs   = 0

        if doc_id not in database[stemmed].docids:
            database[stemmed].docs += 1
            database[stemmed].docids[doc_id] = 0

        database[stemmed].docids[doc_id] += 1


# ==============================================================================
# flush_block — write in-memory index to SQLite, then clear memory
# ==============================================================================
# Called once per document immediately after process() returns.
# This keeps peak memory usage proportional to a single document's vocabulary,
# not the entire corpus.
#
# TF-IDF is NOT stored here — it is recalculated by write_index_dat() once the
# true total_docs (N) is known.  Storing a TF-IDF mid-run would give wrong
# values because N grows with every document.
#
# DF is accumulated correctly by using INSERT OR IGNORE for the term and then
# doing a separate UPDATE to increment docfreq on existing posting rows, rather
# than overwriting them with INSERT OR REPLACE.
# ==============================================================================

def flush_block(cur):
    """Persist the current in-memory database dict to SQLite then clear it."""
    global database

    for stemmed_term, term_obj in database.items():

        # Write the term once; ignore if it already exists from a prior flush
        cur.execute(
            "INSERT OR IGNORE INTO TermDictionary VALUES (?, ?)",
            (stemmed_term, term_obj.termid)
        )

        for doc_id, tf in term_obj.docids.items():
            # Check whether a posting row already exists for this (term, doc)
            # combination.  Under per-document flushing each doc_id only ever
            # appears once per term in a single flush, so this path is only hit
            # if the same document was somehow processed twice — but the guard
            # is cheap and correct.
            cur.execute(
                "SELECT termfreq, docfreq FROM Posting WHERE TermId = ? AND DocId = ?",
                (term_obj.termid, doc_id)
            )
            existing = cur.fetchone()

            if existing:
                # Accumulate — add this document's TF to whatever was stored
                new_tf  = existing[0] + tf
                new_df  = existing[1]           # df unchanged; same doc
                cur.execute(
                    "UPDATE Posting SET termfreq = ?, tfidf = 0 "
                    "WHERE TermId = ? AND DocId = ?",
                    (new_tf, term_obj.termid, doc_id)
                )
            else:
                # New (term, doc) pair — increment the global DF for this term
                # across all its existing posting rows, then insert the new row.
                cur.execute(
                    "UPDATE Posting SET docfreq = docfreq + 1 WHERE TermId = ?",
                    (term_obj.termid,)
                )
                cur.execute(
                    # tfidf stored as 0 placeholder; recalculated at end
                    "INSERT INTO Posting (TermId, DocId, tfidf, docfreq, termfreq) "
                    "VALUES (?, ?, 0, "
                    "  (SELECT COALESCE(MAX(docfreq), 0) + 1 FROM Posting "
                    "   WHERE TermId = ?), "
                    "?)",
                    (term_obj.termid, doc_id, term_obj.termid, tf)
                )

    database.clear()


# ==============================================================================
# write_index_dat — human-readable flat-file index, cross-platform UTF-8
# ==============================================================================
# Written once at the very end when total_docs (N) is finalised, so every IDF
# value reflects the complete collection rather than a partial snapshot.
#
# Format per term block:
#
#   TERM       : <stemmed term>
#   TERM_ID    : <integer id>
#   DF         : <document frequency>
#   IDF        : <log(N / df)>   [formula shown inline]
#   POSTINGS   :
#                DocId=<id>   TF=<count>   TF-IDF=<score>
#                ...
#   ------------------------------------------------------------------------
# ==============================================================================

def write_index_dat(dat_path, cur, total_docs):
    """
    1. Recompute and persist correct TF-IDF values now that N (total_docs) is
       final and every term's DF has been fully accumulated across all documents.
    2. Write a human-readable index.dat with one block per unique term.
    """
    separator = "-" * 72

    # ── Pass 1: update tfidf column in Posting with correct values ───────────
    # DF is now accurate (accumulated across all docs during flush_block).
    # We recalculate IDF = log(N / df) and tfidf = tf * idf for every row.
    cur.execute("SELECT TermId, DocId, termfreq, docfreq FROM Posting")
    all_rows = cur.fetchall()

    for (term_id, doc_id, tf, df) in all_rows:
        idf   = math.log(total_docs / float(df)) if df > 0 and total_docs > 0 else 0.0
        tfidf = tf * idf
        cur.execute(
            "UPDATE Posting SET tfidf = ? WHERE TermId = ? AND DocId = ?",
            (tfidf, term_id, doc_id)
        )

    # ── Pass 2: write index.dat ───────────────────────────────────────────────
    with open(dat_path, 'w', encoding='utf-8') as f:

        f.write("=" * 72 + "\n")
        f.write("  INVERTED INDEX — index.dat\n")
        f.write("  Total documents (N) : %d\n" % total_docs)
        f.write("  Generated           : %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("=" * 72 + "\n\n")

        cur.execute("SELECT Term, TermId FROM TermDictionary ORDER BY TermId")
        all_terms = cur.fetchall()

        for (term, term_id) in all_terms:

            cur.execute(
                """SELECT DocId, termfreq, docfreq, tfidf
                   FROM Posting
                   WHERE TermId = ?
                   ORDER BY DocId""",
                (term_id,)
            )
            postings = cur.fetchall()

            if not postings:
                continue

            df  = postings[0][2]    # same for every row of this term
            idf = math.log(total_docs / float(df)) if df > 0 and total_docs > 0 else 0.0

            f.write("TERM       : %s\n"                        % term)
            f.write("TERM_ID    : %d\n"                        % term_id)
            f.write("DF         : %d\n"                        % df)
            f.write("IDF        : %.6f  [log(%d / %d)]\n"     % (idf, total_docs, df))
            f.write("POSTINGS   :\n")

            for (doc_id, tf, _df, tfidf) in postings:
                f.write(
                    "             DocId=%-6d  TF=%-5d  TF-IDF=%.6f\n"
                    % (doc_id, tf, tfidf)
                )

            f.write(separator + "\n\n")

    print("index.dat written  : %s" % dat_path)


# ==============================================================================
# process — open and tokenise a single file line by line
# ==============================================================================

def process(filename, doc_id, cur):
    try:
        with open(filename, 'r', errors='ignore') as f:
            for line in f:
                parsetoken(line, doc_id, cur)
    except IOError:
        print("Error reading file: %s" % filename)
        return False
    return True


# ==============================================================================
# walkdir — recursive directory traversal
# ==============================================================================

def walkdir(cur, dirname):
    global documents

    entries = [
        f for f in os.listdir(dirname)
        if os.path.isdir(os.path.join(dirname, f)) or
           os.path.isfile(os.path.join(dirname, f))
    ]

    for f in entries:
        full_path = os.path.join(dirname, f)

        if os.path.isdir(full_path):
            walkdir(cur, full_path)
        else:
            documents += 1
            doc_id = documents

            cur.execute(
                "INSERT INTO DocumentDictionary VALUES (?, ?)",
                (full_path, doc_id)
            )

            # Tokenise and index the file
            process(full_path, doc_id, cur)

            # ── Flush memory after every complete document ──────────────────
            # database.clear() is called inside flush_block, so after this
            # line the in-memory dict is empty and ready for the next file.
            flush_block(cur)

    return True


# ==============================================================================
# Main
# ==============================================================================

if __name__ == '__main__':

    t_start = time.localtime()
    print('\033[31mStart Time:\033[0m %.2d:%.2d' % (t_start.tm_hour, t_start.tm_min))

    # ── Configuration ─────────────────────────────────────────────────────────
    folder   = "cacm"   # path to your document corpus
    db_path  = "indexer_part3.db" # SQLite database output
    dat_path = "index.dat"        # human-readable flat index file
    # ──────────────────────────────────────────────────────────────────────────

    con = sqlite3.connect(db_path)
    con.isolation_level = None       # autocommit — every INSERT lands immediately
    cur = con.cursor()

    # Document Dictionary
    cur.execute("DROP TABLE IF EXISTS DocumentDictionary")
    cur.execute("DROP INDEX IF EXISTS idxDocumentDictionary")
    cur.execute("CREATE TABLE IF NOT EXISTS DocumentDictionary (DocumentName TEXT, DocId INT)")
    cur.execute("CREATE INDEX IF NOT EXISTS idxDocumentDictionary ON DocumentDictionary (DocId)")

    # Term Dictionary
    cur.execute("DROP TABLE IF EXISTS TermDictionary")
    cur.execute("DROP INDEX IF EXISTS idxTermDictionary")
    cur.execute("CREATE TABLE IF NOT EXISTS TermDictionary (Term TEXT, TermId INT)")
    cur.execute("CREATE INDEX IF NOT EXISTS idxTermDictionary ON TermDictionary (TermId)")

    # Postings  (TermId, DocId, tfidf, docfreq, termfreq)
    cur.execute("DROP TABLE IF EXISTS Posting")
    cur.execute("DROP INDEX IF EXISTS idxPosting1")
    cur.execute("DROP INDEX IF EXISTS idxPosting2")
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

    # ── Index the corpus ──────────────────────────────────────────────────────
    walkdir(cur, folder)

    t_index = time.localtime()
    print('\033[31mIndexing Complete\033[0m: %.2d:%.2d' % (t_index.tm_hour, t_index.tm_min))

    # Safety net: flush anything left in memory (normally empty after walkdir)
    if database:
        flush_block(cur)

    # ── Write index.dat ───────────────────────────────────────────────────────
    """
    Redacted Write File Line
    It could be commented if you would like to write out an index dat file
    but, I have uncommented it as index.dat is a preqreuisite for our search
    engine files (Code_Indexer_part5.py)
    """
    write_index_dat(dat_path, cur, documents)
    

    con.commit()
    con.close()

    # ── Final Statistics ──────────────────────────────────────────────────────
    t_end = time.localtime()
    print("\033[34m========== Indexer Statistics ==========\033[0m")
    print("\033[90mDocuments processed\033[0m      : %d" % documents)
    print("\033[90mTotal tokens parsed\033[0m      : %d" % tokens)
    print("\033[90mUnique terms in index\033[0m    : %d" % terms)
    print("\033[90mStop word matches\033[0m        : %d" % stop_word_hits)
    print("\033[90mEnd Time\033[0m                 : %.2d:%.2d" % (t_end.tm_hour, t_end.tm_min))
    print("\033[34m=========================================\033[0m")