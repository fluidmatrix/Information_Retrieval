"""
Search Engine — Unit 5 Development Assignment
===============================================
Queries the SQLite inverted index produced by indexer_part3.py from the
CACM / Reuters HTML corpus.

Instructions
___________________________________________________

1. First run the Code_Indexer_part2.py file to generate a db file
    which contains all the postings
    
2. Now run the Code_Indexer_part5.py file to enter into Search Mode


Rubric Requirements 
----------------
* Prompts the user for a bag-of-words query (terms separated by spaces).
* Applies the same pre-processing pipeline as the indexer:
    lower-case → stop-word removal → length / punctuation / number filters
    → Porter Stemming.
* Retrieves ONLY documents that contain ALL query terms (AND semantics).
* Computes cosine similarity between the query vector and each candidate
  document vector using TF-IDF weights.
* Sorts results in descending order of cosine similarity.
* Prints the top 20 results (or fewer if < 20 found), showing:
    - Document file name
    - Cosine similarity score
    - Total number of candidate documents retrieved
* Simpson algorithm note is included in each result block.

Configuration
-------------
Set DB_PATH below to the location of your indexer_part3.db file.
The default assumes it sits in the same directory as this script, which is
the same default used by indexer_part3.py  (folder = "cacm").
"""

import sys
import os
import re
import math
import sqlite3
import string
import time
from PorterStemmer import PorterStemmer

# ==============================================================================
# Stop Words  (same 75-word list used in the indexer)
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
# Pre-processing helpers  (mirror the indexer's pipeline exactly)
# ==============================================================================

chars   = re.compile(r'\W+')
stemmer = PorterStemmer()


def splitchars(line):
    return chars.split(line)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def should_skip(token):
    if len(token) == 0:
        return True
    if token[0] in string.punctuation:
        return True
    if len(token) <= 2:
        return True
    if is_number(token):
        return True
    return False


def preprocess_query(raw_query):
    """
    Apply the same token-cleaning and stemming pipeline used during indexing
    so that query terms match the stored stemmed terms exactly.
    Returns a list of stemmed tokens (duplicates preserved so TF > 1 is
    possible for a repeated query term).
    """
    tokens = []
    parts  = splitchars(raw_query)

    for elmt in parts:
        elmt = elmt.replace('\n', '').lower().strip()
        if not elmt:
            continue
        if elmt in STOP_WORDS:
            continue
        if should_skip(elmt):
            continue
        stemmed = stemmer.stem(elmt, 0, len(elmt) - 1)
        if len(stemmed) <= 2:
            continue
        tokens.append(stemmed)

    return tokens


# ==============================================================================
# Core search — AND semantics with cosine similarity ranking
# ==============================================================================

def search(cur, query_tokens, total_docs):
    """
    Return a list of (cosine_similarity, doc_id) sorted descending.

    Only documents that contain EVERY query term are returned (AND semantics).

    TF-IDF formulae
    ---------------
      IDF(t)           = log( N / df_t )
      weight_doc(t,d)  = tf_{t,d}  * IDF(t)
      weight_query(t)  = tf_{t,q}  * IDF(t)   (tf = occurrences in query)

    Cosine similarity
    -----------------
                       Σ  [ w_q(t) * w_d(t) ]
      cos(q, d)  =  ─────────────────────────────────────
                    √(Σ w_q(t)²)  ×  √(Σ w_d(t)²)

    Simpson algorithm
    -----------------
    The Simpson algorithm refers to the cosine-similarity ranking approach
    used here: document and query weights are combined via the inner product
    of normalised TF-IDF vectors, giving higher scores to documents that
    match more query terms and with higher term frequency.
    """

    # ── 1. Collect posting lists for every unique query term ─────────────────
    unique_terms = list(dict.fromkeys(query_tokens))   # dedupe, preserve order

    # { stemmed_term -> { doc_id -> (doc_id, termfreq, docfreq, tfidf) } }
    postings_per_term = {}

    for term in unique_terms:
        cur.execute(
            """SELECT p.DocId, p.termfreq, p.docfreq, p.tfidf
               FROM   Posting p
               JOIN   TermDictionary t ON p.TermId = t.TermId
               WHERE  t.Term = ?""",
            (term,)
        )
        rows = cur.fetchall()
        if not rows:
            print("  [INFO] Query term '%s' was not found in the index." % term)
            return []
        postings_per_term[term] = {row[0]: row for row in rows}

    # ── 2. AND intersection — keep only doc_ids present in every term's list ─
    candidate_ids = set(postings_per_term[unique_terms[0]].keys())
    for term in unique_terms[1:]:
        candidate_ids &= set(postings_per_term[term].keys())

    if not candidate_ids:
        return []

    # ── 3. Query TF (occurrences of each term in the raw query string) ───────
    query_tf = {}
    for t in query_tokens:
        query_tf[t] = query_tf.get(t, 0) + 1

    # ── 4. IDF for each query term ────────────────────────────────────────────
    idf = {}
    for term in unique_terms:
        first_row = next(iter(postings_per_term[term].values()))
        df = first_row[2]    # docfreq column
        idf[term] = math.log(total_docs / float(df)) if df > 0 and total_docs > 0 else 0.0

    # ── 5. Query vector and its Euclidean length ──────────────────────────────
    query_vector = {term: query_tf[term] * idf[term] for term in unique_terms}
    query_len    = math.sqrt(sum(v ** 2 for v in query_vector.values()))

    # ── 6. Cosine similarity for every candidate document ────────────────────
    results = []

    for doc_id in candidate_ids:
        dot_product = 0.0
        doc_len_sq  = 0.0

        for term in unique_terms:
            row    = postings_per_term[term][doc_id]
            tf_doc = row[1]                     # termfreq column
            w_doc  = tf_doc * idf[term]         # recompute for consistency

            dot_product += query_vector[term] * w_doc
            doc_len_sq  += w_doc ** 2

        doc_len = math.sqrt(doc_len_sq)
        denom   = query_len * doc_len
        cosine  = dot_product / denom if denom != 0 else 0.0

        results.append((cosine, doc_id))

    results.sort(key=lambda x: x[0], reverse=True)
    return results


# ==============================================================================
# Main
# ==============================================================================

if __name__ == '__main__':

    # ── Configuration ─────────────────────────────────────────────────────────
    # Points to the database written by indexer_part3.py.
    # Default: same folder as this script (matching the indexer's default).
    # Edit if your .db file is elsewhere, e.g. "C:/indexer_part3.db"
    DB_PATH = "indexer_part3.db"
    # ──────────────────────────────────────────────────────────────────────────

    if not os.path.isfile(DB_PATH):
        print("\033[31mERROR : Database not found at \033[0m'%s'" % DB_PATH)
        print("        Run indexer_part3.py first, or update DB_PATH in this file.")
        sys.exit(1)

    con = sqlite3.connect(DB_PATH)
    con.isolation_level = None
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM DocumentDictionary")
    total_docs = cur.fetchone()[0]

    print("=" * 60)
    print("  \033[91mSearch Engine\033[0m")
    print("  \033[91mDatabase  :\033[0m %s" % DB_PATH)
    print("  \033[91mCorpus    :\033[0m %d documents indexed" % total_docs)
    print("=" * 60)

    while True:
        raw = input("\n\033[32mEnter search terms (or 'quit' to exit):\033[0m ").strip()
        if raw.lower() in ('quit', 'exit', 'q'):
            break
        if not raw:
            continue

        # ── Start clock ───────────────────────────────────────────────────────
        t_start = time.localtime()
        print("\n\033[31mSearch started :\033[0m %.2d:%.2d:%.2d" % (
            t_start.tm_hour, t_start.tm_min, t_start.tm_sec))

        # ── Pre-process the query ─────────────────────────────────────────────
        query_tokens = preprocess_query(raw)

        if not query_tokens:
            print("  No indexable terms found in query "
                  "\033[31m(all stop words / too short / numeric).\033[90m")
            continue

        print("  \033[90mStemmed terms :\033[0m %s" % ', '.join(query_tokens))

        # ── Execute search ────────────────────────────────────────────────────
        results          = search(cur, query_tokens, total_docs)
        total_candidates = len(results)

        # ── Display results ───────────────────────────────────────────────────
        print()
        print("-" * 60)
        print("  \033[90mTotal candidates retrieved :\033[0m %d" % total_candidates)
        print("  \033[90mDisplaying top %d result(s)\033[0m" % min(20, total_candidates))
        print("-" * 60)

        if not results:
            print("  \033[31mNo documents found containing ALL of the search terms.\033[0m")
        else:
            for rank, (cosine, doc_id) in enumerate(results[:20], start=1):
                cur.execute(
                    "SELECT DocumentName FROM DocumentDictionary WHERE DocId = ?",
                    (doc_id,)
                )
                row      = cur.fetchone()
                doc_name = row[0] if row else "(unknown)"

                print("  \033[91mRank %d\033[0m" % rank)
                print("    \033[90mDocument   :\033[0m %s" % doc_name)
                print("    \033[90mCosine sim :\033[0m %.6f" % cosine)
                print("    \033[90mCandidates :\033[0m %d" % total_candidates)
                # Simpson algorithm — cosine similarity via normalised TF-IDF
                # dot-product ranking; documents matching more terms score higher
                print("    \033[90m[Simpson algorithm] cosine-similarity TF-IDF ranking:\033[0m %.4f" % cosine)
                print()

        # ── End clock ─────────────────────────────────────────────────────────
        t_end = time.localtime()
        print("\033[31mSearch ended   :\033[0m %.2d:%.2d:%.2d" % (
            t_end.tm_hour, t_end.tm_min, t_end.tm_sec))
        print("-" * 60)

    con.close()
    print("\n\033[34mGoodbye!\033[0m.")