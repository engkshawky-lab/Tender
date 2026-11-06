"""Arabic / English text normalisation and lightweight similarity search (character n-gram TF-IDF).
Used for auto cost-coding, finding the nearest historical item, and document retrieval for the chat assistant.
Deterministic and offline; can be swapped for vector embeddings later without changing callers."""
import math
import re
from collections import Counter

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[ً-ْٰـ]")


def normalize(text: str) -> str:
    if not text:
        return ""
    t = str(text).translate(_AR_DIGITS)
    t = _DIACRITICS.sub("", t)
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    t = t.lower()
    t = re.sub(r"[^\w\s.%/]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def to_number(v):
    """Parse numbers that may come as text with thousands separators or Arabic-Indic digits."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).translate(_AR_DIGITS).replace("٬", "").replace(",", "").replace("٫", ".").strip()
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ngrams(text: str, n: int = 3) -> Counter:
    t = normalize(text)
    grams: Counter = Counter()
    for word in t.split():
        w = f" {word} "
        if len(w) <= n:
            grams[w] += 1
        for i in range(len(w) - n + 1):
            grams[w[i:i + n]] += 1
    return grams


class TfIdfIndex:
    def __init__(self, docs: list[tuple[object, str]]):
        self.keys = [k for k, _ in docs]
        self.vecs = [ngrams(t) for _, t in docs]
        df: Counter = Counter()
        for v in self.vecs:
            df.update(v.keys())
        n = max(1, len(docs))
        self.idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self.wvecs = [self._weight(v) for v in self.vecs]

    def _weight(self, v: Counter) -> dict:
        w = {g: c * self.idf.get(g, 1.0) for g, c in v.items()}
        norm = math.sqrt(sum(x * x for x in w.values())) or 1.0
        return {g: x / norm for g, x in w.items()}

    def search(self, query: str, k: int = 5, min_score: float = 0.0):
        q = self._weight(ngrams(query))
        scored = []
        for key, w in zip(self.keys, self.wvecs):
            s = sum(x * w.get(g, 0.0) for g, x in q.items())
            if s > min_score:
                scored.append((s, key))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]
