#!/usr/bin/env python3
"""
Build books.json from cache sources.
Merges toanmath_posts, shop_nsgd, shop_nhanvan, mccme_biblio, mathru, and page data.
Keeps existing 45 entries; adds new books for grades 6-9 advanced math (HSG, olympiad).
Deduplicates by normalized title; saves atomically.
"""

import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

CACHE_DIR = Path("/home/luongminhthu/Documents/code/my_app/ruatoan/.cache/books")
BOOKS_FILE = Path("/home/luongminhthu/Documents/code/my_app/ruatoan/content/books.json")
GRADES_6_9 = (6, 7, 8, 9, 10)  # 10 = vào 10 chuyên


def normalize_title(title):
    """Normalize title for deduplication."""
    s = unicodedata.normalize("NFKD", title.lower())
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def make_slug(title):
    """Create kebab-case slug from title."""
    s = unicodedata.normalize("NFKD", title.lower())
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:60] if len(s) > 60 else s


def extract_topics(title, desc=""):
    """Extract topics from title/desc keywords."""
    topics = set()
    text = (title + " " + desc).lower()

    if any(w in text for w in ["đại số", "phương trình", "bất phương"]):
        topics.add("dai-so")
    if any(w in text for w in ["bất đẳng thức", "bdt", "inequality"]):
        topics.add("bat-dang-thuc")
    if any(w in text for w in ["hình học", "hình phẳng", "hình không gian", "geometry"]):
        topics.add("hinh-hoc")
    if any(w in text for w in ["tổ hợp", "đếm", "combination", "permutation"]):
        topics.add("to-hop")
    if any(w in text for w in ["số học", "ước số", "số nguyên", "number theory"]):
        topics.add("so-hoc")
    if any(w in text for w in ["phương trình diophantine", "nghiệm nguyên", "integer solution"]):
        topics.add("nghiem-nguyen")

    return sorted(list(topics)) if topics else ["dai-so", "hinh-hoc"]


def is_relevant_book(title, desc="", grade_hints=""):
    """Check if book is relevant (advanced math for grades 6-9 HSG/olympiad)."""
    title_lower = title.lower()

    # HARD SKIP: non-math, standard textbooks, low/high grades, non-serious materials
    hard_skip = [
        "sách giáo khoa", "sgk", "sách bài tập", "sbt",
        "casio", "máy tính", "mtct", "khoa học máy tính",
        "tiếng anh", "tiếng việt", "hóa học", "vật lý", "vật lí",
        "sinh học", "lịch sử", "địa lý", "địa lí", "công dân", "kỹ năng sống",
        "tiểu học", "mầm non", "lớp 1", "lớp 2", "lớp 3", "lớp 4", "lớp 5",
        "lớp 10", "lớp 11", "lớp 12", "lớp 13", "lớp a", "lớp b", "lớp c",
        "thpt", "cao đẳng", "đại học",
        "truyện", "văn học", "soạn bài", "tiểu thuyết", "ngữ văn", "tác phẩm",
        "tâm thế", "kỹ năng", "tự tin",
        "calendar", "календарь", "загадок", "puzzle",
        "kinh tế", "quản lý", "business",
        "лингвистика", "linguistics", "ngôn ngữ",
    ]
    for skip in hard_skip:
        if skip in title_lower:
            return False

    # Also skip "đề thi" or exams for grade 10+ even if HSG
    if ("đề" in title_lower) and any(g in title_lower for g in ["10", "11", "12", "thpt"]):
        return False

    # Tier 1: Explicit HSG/Olympiad for THCS (not THPT)
    if any(kw in title_lower for kw in ["hsg", "học sinh giỏi"]):
        if not any(kw in title_lower for kw in ["thpt", "lớp 10", "lớp 11", "lớp 12"]):
            if "violympic" not in title_lower:
                return True

    # Tier 1b: Olympiad (not Violympic, not THPT)
    if any(kw in title_lower for kw in ["olympiad", "olympic", "олимпиада"]):
        if "violympic" not in title_lower:
            if not any(kw in title_lower for kw in ["thpt", "lớp 10", "lớp 11", "lớp 12"]):
                return True

    # Tier 1c: Explicit "vào 10 chuyên"
    if any(kw in title_lower for kw in ["vào 10 chuyên", "vào lớp 10 chuyên", "thi chuyên", "tuyển sinh chuyên", "оху"]):
        return True

    # Tier 2: Advanced + math topic (THCS only)
    has_level = any(kw in title_lower for kw in [
        "nâng cao", "bồi dưỡng", "chuyên sâu",
        "chuyên đề nâng cao", "tuyển tập",
    ])

    has_topic = any(kw in title_lower for kw in [
        "bất đẳng thức", "bdt", "inequality",
        "phương trình", "số học", "tổ hợp", "đếm", "hình học",
        "problem", "problem solving", "задач", "задачник",
    ])

    if has_level and has_topic:
        if not any(kw in title_lower for kw in ["thpt", "lớp 10", "lớp 11", "lớp 12", "cao đẳng", "đại học"]):
            return True

    return False


def extract_grades(title, desc=""):
    """Extract grade levels from title/desc."""
    text = (title + " " + desc).lower()
    grades = set()

    for i in range(6, 11):
        if f"lớp {i}" in text or f"toán {i}" in text or f"grade {i}" in text:
            grades.add(i)

    # Default to 6-9 if no specific grade found but looks like THCS
    if "thcs" in text or "toán" in text:
        if not grades:
            grades = {6, 7, 8, 9}

    return sorted(list(grades)) if grades else [6, 7, 8, 9]


def process_toanmath_posts():
    """Process toanmath_posts.json."""
    books = []
    path = CACHE_DIR / "toanmath_posts.json"
    if not path.exists():
        return books

    with open(path) as f:
        posts = json.load(f)

    for post in posts:
        title = post.get("title", "").strip()
        if not title or not is_relevant_book(title):
            continue

        # Decode HTML entities
        title = title.replace("&#8211;", "–").replace("&#8212;", "—")
        title = title.replace("&amp;", "&").replace("&quot;", '"')

        book = {
            "title": title,
            "url": post.get("link", ""),
            "source": "thcs.toanmath.com",
            "lang": "vi",
            "free": True,
            "grades": extract_grades(title),
            "topics": extract_topics(title),
            "stage": 2,
            "kind": "book",
        }
        books.append(book)

    return books


def process_shop_products(shop_file, vendor_name, free=False):
    """Process shop product files (shop_nsgd_all.json, shop_nhanvan.json)."""
    books = []
    path = CACHE_DIR / shop_file
    if not path.exists():
        return books

    with open(path) as f:
        products = json.load(f)

    for prod in products:
        title = prod.get("name", "").strip()
        if not title or not is_relevant_book(title, prod.get("desc", "")):
            continue

        # Build URL
        handle = prod.get("handle", "")
        if shop_file == "shop_nhanvan.json":
            store = prod.get("store", "https://nhanvan.vn")
            url = f"{store}/{handle}" if handle else ""
            source = "nhanvan.vn"
        else:
            url = f"https://shop.nsgd.vn/{handle}" if handle else ""
            source = "nsgd.vn"

        if not url:
            continue

        book = {
            "title": title,
            "url": url,
            "source": source,
            "lang": "vi",
            "free": free,
            "grades": extract_grades(title, prod.get("desc", "")),
            "topics": extract_topics(title, prod.get("desc", "")),
            "stage": 2,
            "kind": "book",
        }
        if prod.get("vendor"):
            book["publisher"] = prod["vendor"]

        books.append(book)

    return books


def process_mccme_biblio():
    """Process mccme_biblio.json (Russian classical books)."""
    books = []
    path = CACHE_DIR / "mccme_biblio.json"
    if not path.exists():
        return books

    with open(path) as f:
        items = json.load(f)

    for item in items:
        title = item.get("title", "").strip()
        if not title or not is_relevant_book(title):
            continue

        # MCCME are Russian math classics, generally relevant
        book = {
            "title": title,
            "url": item.get("node", ""),
            "source": "mccme.ru",
            "lang": "ru",
            "free": True,
            "grades": [6, 7, 8, 9],  # Assume THCS level
            "topics": extract_topics(title),
            "stage": 2,
            "kind": "book",
        }
        books.append(book)

    return books


def process_mathru_rows():
    """Process mathru_rows.json (Russian math library)."""
    books = []
    path = CACHE_DIR / "mathru_rows.json"
    if not path.exists():
        return books

    with open(path) as f:
        rows = json.load(f)

    for row in rows:
        title = row.get("title", "").strip()
        if not title or not is_relevant_book(title):
            continue

        book = {
            "title": title,
            "url": row.get("link", ""),
            "source": "math.ru",
            "lang": "ru",
            "free": True,
            "grades": [6, 7, 8, 9],
            "topics": extract_topics(title),
            "stage": 2,
            "kind": "book",
        }

        if row.get("author"):
            book["author"] = row["author"]
        if row.get("year"):
            book["publisher"] = f"{row['year']}"

        books.append(book)

    return books


def process_olib_files():
    """Process olib/ OpenLibrary JSON results."""
    books = []
    olib_dir = CACHE_DIR / "olib"
    if not olib_dir.exists():
        return books

    for fname in olib_dir.glob("*.json"):
        try:
            with open(fname) as f:
                data = json.load(f)

            docs = data.get("docs", [])
            for doc in docs:
                title = doc.get("title", "").strip()
                if not title or not is_relevant_book(title):
                    continue

                book = {
                    "title": title,
                    "url": f"https://openlibrary.org{doc.get('key', '')}",
                    "source": "openlibrary.org",
                    "lang": "en",
                    "free": True,
                    "grades": [6, 7, 8, 9],
                    "topics": extract_topics(title),
                    "stage": 2,
                    "kind": "book",
                }

                authors = doc.get("author_name", [])
                if authors:
                    book["author"] = "; ".join(authors[:3])

                if doc.get("publisher"):
                    book["publisher"] = "; ".join(doc["publisher"][:2])

                books.append(book)
        except Exception:
            pass

    return books


def process_tm_candidates():
    """Process tm_candidates.txt (toanmath candidates)."""
    books = []
    path = CACHE_DIR / "tm_candidates.txt"
    if not path.exists():
        return books

    with open(path) as f:
        lines = f.readlines()

    # Skip header
    if lines and lines[0].strip().isdigit():
        lines = lines[1:]

    for line in lines:
        line = line.strip()
        if not line or "|" not in line:
            continue

        parts = line.split("|", 1)
        if len(parts) != 2:
            continue

        url = parts[0].strip()
        title = parts[1].strip()

        if not title or not is_relevant_book(title):
            continue

        title = title.replace("&#8211;", "–").replace("&#8212;", "—")

        book = {
            "title": title,
            "url": url,
            "source": "thcs.toanmath.com",
            "lang": "vi",
            "free": True,
            "grades": extract_grades(title),
            "topics": extract_topics(title),
            "stage": 2,
            "kind": "book",
        }
        books.append(book)

    return books


def load_existing():
    """Load existing books.json."""
    if not BOOKS_FILE.exists():
        return []

    with open(BOOKS_FILE) as f:
        return json.load(f)


def build_books():
    """Build merged books list."""
    # Load existing books
    existing = load_existing()
    existing_titles = {normalize_title(b["title"]) for b in existing}

    # Collect new books from all sources
    all_books = []
    all_books.extend(process_toanmath_posts())
    all_books.extend(process_tm_candidates())
    all_books.extend(process_shop_products("shop_nsgd_all.json", "NSGD", free=False))
    all_books.extend(process_shop_products("shop_nhanvan.json", "NhanVan", free=False))
    all_books.extend(process_mccme_biblio())
    all_books.extend(process_mathru_rows())
    all_books.extend(process_olib_files())

    # Deduplicate new books by normalized title
    seen_new = {}
    for book in all_books:
        norm = normalize_title(book["title"])

        # Skip if duplicate with existing
        if norm in existing_titles:
            continue

        # Keep first occurrence of normalized title
        if norm not in seen_new:
            seen_new[norm] = book

    # Assign IDs to new books
    new_books = []
    for book in seen_new.values():
        if "id" not in book:
            book["id"] = make_slug(book["title"])

        # Ensure id is unique among new books
        base_id = book["id"]
        counter = 1
        while any(b["id"] == book["id"] for b in new_books):
            book["id"] = f"{base_id}-{counter}"
            counter += 1

        new_books.append(book)

    # Merge: keep existing, then add new
    final = existing + new_books

    return final


def save_atomically(data):
    """Save JSON atomically using temp file + rename."""
    # Create temp file in same directory as target
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        dir=BOOKS_FILE.parent,
        text=True
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Atomic rename
        os.replace(tmp_path, BOOKS_FILE)
    except Exception:
        # Clean up temp if failed
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def main():
    books = build_books()
    save_atomically(books)

    # Stats
    total = len(books)
    existing_count = 45
    added = total - existing_count

    # Count by (lang, source)
    stats = Counter()
    for book in books[existing_count:]:  # Only new books
        stats[(book.get("lang", "?"), book.get("source", "?"))] += 1

    print(f"Total: {total} (added {added})")
    print("\nBy (lang, source):")
    for (lang, src), count in sorted(stats.items()):
        print(f"  {lang:2} {src:25} {count:4}")


if __name__ == "__main__":
    main()
