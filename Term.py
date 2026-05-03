

# ==============================================================================
# Term Object
# ==============================================================================

class Term:
    def __init__(self):
        self.termid  = 0
        self.docs    = 0    # document frequency (df)
        self.docids  = {}   # { doc_id: term_freq }