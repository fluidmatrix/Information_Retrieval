# 🔍 Inverted Index — CS 3308 Information Retrieval

A corpus indexer built in Python for the CS 3308 Information Retrieval course. It recursively walks a document collection, applies a full NLP preprocessing pipeline, and builds a weighted inverted index backed by SQLite. All tf-idf scores are computed after the full corpus is processed, ensuring mathematically correct values across the entire collection.

---

## 📋 Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Database Schema](#database-schema)
- [index.dat Format](#indexdat-format)
- [Configuration](#configuration)
- [Running the Indexer](#running-the-indexer)
- [Sample Output](#sample-output)
- [Token Filtering Pipeline](#token-filtering-pipeline)
- [TF-IDF Calculation](#tf-idf-calculation)
- [Memory Management](#memory-management)
- [Dependencies](#dependencies)

---

## ✨ Features

- **Recursive directory traversal** — walks any nested folder structure and indexes every file it finds
- **Porter Stemmer** — full 5-step implementation reduces inflected forms to their common root (`running` → `run`, `algorithm` → `algorithm`)
- **Stop word removal** — 75-word list filtered before stemming for efficiency; stop word hit count reported in final stats
- **Multi-stage token filtering** — removes punctuation-leading tokens, single/double-character tokens, and pure numeric tokens
- **Correct DF accumulation** — document frequency is incremented across documents via SQLite `UPDATE`, not overwritten, so terms appearing in many documents reflect true cross-document counts
- **Deferred TF-IDF scoring** — scores are computed in a single pass at the end when `N` (total document count) is finalised, guaranteeing accuracy
- **Per-document memory flushing** — in-memory index is written to disk and cleared after every document, keeping memory usage bounded regardless of corpus size
- **SQLite backend** — three indexed tables (`DocumentDictionary`, `TermDictionary`, `Posting`) with autocommit
- **`index.dat` human-readable output** — cross-platform UTF-8 flat file showing every term with its `DF`, `IDF`, and per-document `TF` / `TF-IDF` postings
- **Processing statistics** — prints document count, total tokens, unique terms, and stop word hits at completion

---

## 📁 Project Structure

```
.
├── indexer_part3.py   # Main indexer script
├── index.dat          # Generated: human-readable inverted index
├── indexer_part3.db   # Generated: SQLite database
└── README.md
```

---

## ⚙️ How It Works

The indexer follows this pipeline for each document in the corpus:

```
Document File
     │
     ▼
Split into raw tokens  (regex \W+)
     │
     ▼
Lowercase + strip whitespace
     │
     ▼
Stop word filter  ──── match? ──► discard, increment stop_word_hits
     │
     ▼
Structural filters
  • starts with punctuation  ──► discard
  • length ≤ 2               ──► discard
  • pure number              ──► discard
     │
     ▼
Porter Stemmer (5 steps)
     │
     ▼
Post-stem length guard (≤ 2 chars) ──► discard
     │
     ▼
SQLite TermId lookup (reuse existing ID or mint new one)
     │
     ▼
Accumulate in-memory { stemmed_term → Term(termid, docs, docids{}) }
     │
     ▼
[End of document]  →  flush_block()  →  database.clear()
```

After **all** documents are processed, a final pass recomputes TF-IDF with the true `N` and writes `index.dat`.

---

## 🗄️ Database Schema

### `DocumentDictionary`
| Column         | Type | Description                        |
|----------------|------|------------------------------------|
| `DocumentName` | TEXT | Full file path of the document     |
| `DocId`        | INT  | Auto-incrementing document integer |

**Index:** `idxDocumentDictionary` on `DocId`

---

### `TermDictionary`
| Column   | Type | Description                          |
|----------|------|--------------------------------------|
| `Term`   | TEXT | Stemmed term string                  |
| `TermId` | INT  | Unique integer assigned to each term |

**Index:** `idxTermDictionary` on `TermId`

---

### `Posting`
| Column      | Type | Description                                          |
|-------------|------|------------------------------------------------------|
| `TermId`    | INT  | Foreign key → `TermDictionary.TermId`                |
| `DocId`     | INT  | Foreign key → `DocumentDictionary.DocId`             |
| `tfidf`     | REAL | Final weighted TF-IDF score for this (term, doc) pair |
| `docfreq`   | INT  | Number of documents containing this term (DF)        |
| `termfreq`  | INT  | Raw count of term occurrences in this document (TF)  |

**Indexes:** `idxPosting1` on `TermId`, `idxPosting2` on `DocId`

---

## 📄 `index.dat` Format

One block is written per unique term, ordered by `TermId`. The file opens in any text editor on any OS (UTF-8).

```
========================================================================
  INVERTED INDEX — index.dat
  Total documents (N) : 570
  Generated           : 2025-04-01 14:32:07
========================================================================

TERM       : algorithm
TERM_ID    : 42
DF         : 14
IDF        : 3.703124  [log(570 / 14)]
POSTINGS   :
             DocId=12      TF=3      TF-IDF=11.109372
             DocId=87      TF=1      TF-IDF=3.703124
             DocId=203     TF=2      TF-IDF=7.406248
------------------------------------------------------------------------

TERM       : retriev
TERM_ID    : 43
DF         : 31
IDF        : 2.912351  [log(570 / 31)]
POSTINGS   :
             DocId=5       TF=5      TF-IDF=14.561755
             DocId=12      TF=2      TF-IDF=5.824702
------------------------------------------------------------------------
```

> **Note:** Term strings are Porter-stemmed. `retriev` is the stem of *retrieval*, *retrieve*, *retrieves*, etc. Terms with high DF get a low IDF (common across the corpus); terms with low DF get a high IDF (rare and discriminating).

---

## 🔧 Configuration

All three output paths are set at the top of the `__main__` block:

```python
folder   = "c:/reuters_corpus"   # path to your document corpus
db_path  = "c:/indexer_part3.db" # SQLite database output
dat_path = "c:/index.dat"        # human-readable flat index file
```

Change these to match your environment before running. On Linux/macOS use forward-slash paths, e.g. `/home/user/corpus`.

---

## ▶️ Running the Indexer

**Requirements:** Python 3.x (no third-party packages — uses only the standard library)

```bash
python indexer_part3.py
```

The script will print progress timestamps and a final statistics block:

```
Start Time: 14:32
Indexing Complete: 14:35
index.dat written  : c:/index.dat

========== Indexer Statistics ==========
Documents processed      : 570
Total tokens parsed      : 482301
Unique terms in index    : 18742
Stop word matches        : 91430
End Time                 : 14:35
=========================================
```

---

## 📊 Sample Output

### Console

```
Start Time: 09:14
Indexing Complete: 09:17
index.dat written  : c:/index.dat

========== Indexer Statistics ==========
Documents processed      : 570
Total tokens parsed      : 482301
Unique terms in index    : 18742
Stop word matches        : 91430
End Time                 : 09:17
=========================================
```

### SQLite Query Examples

Query all postings for the term `"retriev"`:

```sql
SELECT t.Term, p.DocId, p.termfreq, p.docfreq, p.tfidf
FROM Posting p
JOIN TermDictionary t ON p.TermId = t.TermId
WHERE t.Term = 'retriev'
ORDER BY p.tfidf DESC;
```

Find the top 10 highest-scoring terms in document 42:

```sql
SELECT t.Term, p.termfreq, p.docfreq, p.tfidf
FROM Posting p
JOIN TermDictionary t ON p.TermId = t.TermId
WHERE p.DocId = 42
ORDER BY p.tfidf DESC
LIMIT 10;
```

---

## 🔬 Token Filtering Pipeline

Filters are applied in this exact order, so cheaper checks come first:

| Step | Filter | Example discarded |
|------|--------|-------------------|
| 1 | Stop word match | `the`, `and`, `from` |
| 2 | Begins with punctuation | `'hello`, `.net` |
| 3 | Length ≤ 2 characters | `is`, `go`, `ok` |
| 4 | Pure numeric token | `1993`, `3.14` |
| 5 | Porter Stemming applied | `running` → `run` |
| 6 | Post-stem length ≤ 2 | stems that collapse too short |

---

## 📐 TF-IDF Calculation

The indexer uses the standard vector space model weighting:

$$\text{tf-idf}_{t,d} = \text{tf}_{t,d} \times \text{idf}_t$$

Where:

$$\text{idf}_t = \log\left(\frac{N}{df_t}\right)$$

- **tf** — raw count of term `t` in document `d`
- **df** — number of documents in the collection containing term `t`
- **N** — total number of documents in the collection
- **idf** — uses natural log (`math.log`)

> TF-IDF is computed in a **single final pass** after all documents are indexed. This is important because `N` is only known once the entire corpus has been walked — computing scores mid-run would use an incorrect, partial `N`.

---

## 🧠 Memory Management

The indexer is designed to handle arbitrarily large corpora without running out of memory:

- The in-memory `database` dictionary only ever holds the vocabulary of the **current document** being processed
- Immediately after each document's `process()` call returns, `flush_block()` writes all terms and postings to SQLite and calls `database.clear()`
- There is no fixed term count limit — the bound is one document's vocabulary at a time
- Term IDs are persisted across flushes: `parsetoken()` queries `TermDictionary` before assigning a new ID, so the same term in different documents always maps to the same integer

---

## 📦 Dependencies

| Library   | Use                                      | Source          |
|-----------|------------------------------------------|-----------------|
| `sqlite3` | Persistent inverted index storage        | Python stdlib   |
| `math`    | `log()` for IDF calculation              | Python stdlib   |
| `re`      | Regex tokenisation (`\W+` split)         | Python stdlib   |
| `os`      | Recursive directory walking              | Python stdlib   |
| `string`  | `string.punctuation` for filter check   | Python stdlib   |
| `time`    | Timestamps and `index.dat` generation   | Python stdlib   |

No `pip install` required.

---

## 📜 License

Built for academic use — CS 3308 Information Retrieval, University of the People.
