
# ==============================================================================
# Porter Stemmer (provided, required by rubric - kept as-is with full steps)
# ==============================================================================

class PorterStemmer:
    def __init__(self):
        self.b = ""
        self.k = 0
        self.k0 = 0
        self.j = 0

    def cons(self, i):
        if self.b[i] in ['a', 'e', 'i', 'o', 'u']:
            return 0
        if self.b[i] == 'y':
            if i == self.k0:
                return 1
            else:
                return not self.cons(i - 1)
        return 1

    def m(self):
        n = 0
        i = self.k0
        while True:
            if i > self.j:
                return n
            if not self.cons(i):
                break
            i += 1
        i += 1
        while True:
            while True:
                if i > self.j:
                    return n
                if self.cons(i):
                    break
                i += 1
            i += 1
            n += 1
            while True:
                if i > self.j:
                    return n
                if not self.cons(i):
                    break
                i += 1
            i += 1

    def vowelinstem(self):
        for i in range(self.k0, self.j + 1):
            if not self.cons(i):
                return 1
        return 0

    def doublec(self, j):
        if j < self.k0 + 1:
            return 0
        if self.b[j] != self.b[j - 1]:
            return 0
        return self.cons(j)

    def cvc(self, i):
        if i < self.k0 + 2:
            return 0
        if self.cons(i) or not self.cons(i - 1) or self.cons(i - 2):
            return 0
        ch = self.b[i]
        if ch in ['w', 'x', 'y']:
            return 0
        return 1

    def ends(self, s):
        length = len(s)
        if s[length - 1] != self.b[self.k]:
            return 0
        if length > (self.k - self.k0 + 1):
            return 0
        if self.b[self.k - length + 1:self.k + 1] != s:
            return 0
        self.j = self.k - length
        return 1

    def setto(self, s):
        self.b = self.b[:self.j + 1] + s + self.b[self.k + 1:]
        self.k = self.j + len(s)

    def r(self, s):
        if self.m() > 0:
            self.setto(s)

    def step1ab(self):
        if self.b[self.k] == 's':
            if self.ends("sses"):
                self.k -= 2
            elif self.ends("ies"):
                self.setto("i")
            elif self.b[self.k - 1] != 's':
                self.k -= 1
        if self.ends("eed"):
            if self.m() > 0:
                self.k -= 1
        elif (self.ends("ed") or self.ends("ing")) and self.vowelinstem():
            self.k = self.j
            if self.ends("at"):
                self.setto("ate")
            elif self.ends("bl"):
                self.setto("ble")
            elif self.ends("iz"):
                self.setto("ize")
            elif self.doublec(self.k):
                self.k -= 1
                ch = self.b[self.k]
                if ch in ['l', 's', 'z']:
                    self.k += 1
            elif self.m() == 1 and self.cvc(self.k):
                self.setto("e")

    def step1c(self):
        if self.ends("y") and self.vowelinstem():
            self.b = self.b[:self.k] + 'i' + self.b[self.k + 1:]

    def step2(self):
        if self.ends("ational"):   self.r("ate")
        elif self.ends("tional"):  self.r("tion")
        elif self.ends("enci"):    self.r("ence")
        elif self.ends("anci"):    self.r("ance")
        elif self.ends("izer"):    self.r("ize")
        elif self.ends("abli"):    self.r("able")
        elif self.ends("alli"):    self.r("al")
        elif self.ends("entli"):   self.r("ent")
        elif self.ends("eli"):     self.r("e")
        elif self.ends("ousli"):   self.r("ous")
        elif self.ends("ization"): self.r("ize")
        elif self.ends("ation"):   self.r("ate")
        elif self.ends("ator"):    self.r("ate")
        elif self.ends("alism"):   self.r("al")
        elif self.ends("iveness"): self.r("ive")
        elif self.ends("fulness"): self.r("ful")
        elif self.ends("ousness"): self.r("ous")
        elif self.ends("aliti"):   self.r("al")
        elif self.ends("iviti"):   self.r("ive")
        elif self.ends("biliti"):  self.r("ble")

    def step3(self):
        if self.ends("icate"):    self.r("ic")
        elif self.ends("ative"):  self.setto("")
        elif self.ends("alize"):  self.r("al")
        elif self.ends("iciti"):  self.r("ic")
        elif self.ends("ical"):   self.r("ic")
        elif self.ends("ful"):    self.setto("")
        elif self.ends("ness"):   self.setto("")

    def step4(self):
        if self.ends("al"):       pass
        elif self.ends("ance"):   pass
        elif self.ends("ence"):   pass
        elif self.ends("er"):     pass
        elif self.ends("ic"):     pass
        elif self.ends("able"):   pass
        elif self.ends("ible"):   pass
        elif self.ends("ant"):    pass
        elif self.ends("ement"):  pass
        elif self.ends("ment"):   pass
        elif self.ends("ent"):    pass
        elif self.ends("ion"):
            if self.b[self.j] not in ['s', 't']:
                return
        elif self.ends("ou"):     pass
        elif self.ends("ism"):    pass
        elif self.ends("ate"):    pass
        elif self.ends("iti"):    pass
        elif self.ends("ous"):    pass
        elif self.ends("ive"):    pass
        elif self.ends("ize"):    pass
        else:
            return
        if self.m() > 1:
            self.k = self.j

    def step5(self):
        self.j = self.k
        if self.b[self.k] == 'e':
            a = self.m()
            if a > 1 or (a == 1 and not self.cvc(self.k - 1)):
                self.k -= 1
        if self.b[self.k] == 'l' and self.doublec(self.k) and self.m() > 1:
            self.k -= 1

    def stem(self, p, i, j):
        self.b = p
        self.k = j
        self.k0 = i
        if self.k <= self.k0 + 1:
            return self.b
        self.step1ab()
        self.step1c()
        self.step2()
        self.step3()
        self.step4()
        self.step5()
        return self.b[self.k0:self.k + 1]
