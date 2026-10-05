import csv
import json
import re
import time
from datetime import datetime, timezone

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "mkr1/1.0", "Accept": "application/sparql-results+json"}

COLUMNS = {
    "q1": ["item", "itemLabel", "value", "website"],
    "q2": ["region", "regionLabel", "cnt"],
    "q3": ["item", "itemLabel", "region", "regionLabel", "population"],
}


def run_query(query, retries=4):
    for attempt in range(retries):
        resp = requests.get(ENDPOINT, params={"query": query, "format": "json"},
                            headers=HEADERS, timeout=120)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            wait = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["results"]["bindings"]


def execute(name):
    with open(f"{name}.rq", encoding="utf-8") as f:
        query = f.read()
    bindings = run_query(query)
    cols = COLUMNS[name]
    rows = [{c: b.get(c, {}).get("value", "") for c in cols} for b in bindings]
    with open(f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} рядків -> {name}.csv")
    return rows


def halve_threshold():
    with open("q1.rq", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"FILTER\s*\(\s*\?v\s*>\s*(\d+(?:\.\d+)?)\s*\)", text)
    new = float(m.group(1)) / 2
    new_s = str(int(new)) if new == int(new) else str(new)
    text = text[:m.start(1)] + new_s + text[m.end(1):]
    with open("q1.rq", "w", encoding="utf-8") as f:
        f.write(text)
    return new_s


def main():
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    q1 = execute("q1")
    note = None
    if len(q1) < 5:
        new_threshold = halve_threshold()
        q1 = execute("q1")
        note = (f"Примітка: q1 повернув менше 5 рядків, тому поріг зменшено вдвічі "
                f"- до {new_threshold}.")
    q2 = execute("q2")
    q3 = execute("q3")

    with open("meta.json", "w", encoding="utf-8") as f:
        json.dump({"retrieved_at": retrieved_at}, f, ensure_ascii=False, indent=2)

    def first(rows, *cols):
        return [rows[0][c] for c in cols] if rows else ["-"] * len(cols)

    n1, v1 = first(q1, "itemLabel", "value")
    n2, c2 = first(q2, "regionLabel", "cnt")
    (p3,) = first(q3, "population")
    lines = [f"Q1: {n1} - {v1}", f"Q2: {n2} - {c2}", f"Q3: {p3}"]
    if note:
        lines.append(note)
    with open("ANSWERS.md", "w", encoding="utf-8") as f:
        f.write("\n\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
