import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

EX = "http://example.org/mkr/"
PREFIXES = {
    "ex": EX,
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

_BAD_IRI_CHARS = re.compile(r'[\x00-\x20<>"{}|^`\\]')


def iri(path):
    path = path.strip().replace(" ", "_")
    path = _BAD_IRI_CHARS.sub(lambda m: "%%%02X" % ord(m.group()), path)
    return f"<{EX}{path}>"


def ex(name):
    return f"ex:{name}"


def lit_str(text, lang=None):
    esc = (text.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r"))
    return f'"{esc}"@{lang}' if lang else f'"{esc}"'


def lit_typed(lexical, datatype):
    return f'"{lexical}"^^{datatype}'


class Graph:
    

    def __init__(self):
        self.data = {}

    def add(self, s, p, o):
        objs = self.data.setdefault(s, {}).setdefault(p, [])
        if o not in objs:
            objs.append(o)

    def serialize(self, path):
        lines = [f"@prefix {k}: <{v}> ." for k, v in PREFIXES.items()]
        lines.append("")
        for s in self.data:
            preds = self.data[s]
            lines.append(s)
            items = list(preds.items())
            for i, (p, objs) in enumerate(items):
                pred = "a" if p == "rdf:type" else p
                end = " ." if i == len(items) - 1 else " ;"
                lines.append(f"    {pred} {', '.join(objs)}{end}")
            lines.append("")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))


def norm_id(v):
    return v.strip().upper()


def norm_city(v):
    return v.strip().title()


def parse_date(v):
    v = v.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Невідомий формат дати: {v!r}")


def parse_price(v):
    v = v.strip()
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_note(note):
    """'delay=25;by=AirWatch' -> {'delay': '25', 'by': 'AirWatch'}"""
    result = {}
    for part in (note or "").split(";"):
        if "=" in part:
            k, val = part.split("=", 1)
            result[k.strip().lower()] = val.strip()
    return result


def load_flights(csv_path):
    flights = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = norm_id(row["flight_id"])
            rec = {
                "airline": row["airline"].strip(),
                "from_city": norm_city(row["from_city"]),
                "from_country": row["from_country"].strip(),
                "to_city": norm_city(row["to_city"]),
                "to_country": row["to_country"].strip(),
                "date": parse_date(row["dep_date"]),
                "duration": int(row["duration_min"].strip()),
                "price": parse_price(row["price_eur"]),
                "note": (row.get("note") or "").strip(),
            }
            if fid not in flights:
                flights[fid] = rec
            else:  
                old = flights[fid]
                for k, v in rec.items():
                    if old.get(k) in (None, "") and v not in (None, ""):
                        old[k] = v
    return flights


CLASSES = ["Flight", "Airline", "City", "Country", "Source"]
PROPERTIES = [
    ("operatedBy", ex("Flight"), ex("Airline")),
    ("departsFrom", ex("Flight"), ex("City")),
    ("arrivesAt", ex("Flight"), ex("City")),
    ("locatedIn", ex("City"), ex("Country")),
    ("departureDate", ex("Flight"), "xsd:date"),
    ("durationMin", ex("Flight"), "xsd:integer"),
    ("priceEur", ex("Flight"), "xsd:decimal"),
    ("hasDelayMinutes", ex("Flight"), "xsd:integer"),
    ("reportedBy", "rdf:Statement", ex("Source")),
    ("fromBusyCountry", ex("Flight"), "xsd:boolean"),
]


def add_schema(g):
    for c in CLASSES:
        g.add(ex(c), "rdf:type", "rdfs:Class")
    for c in ("BudgetFlight", "LongFlight"):
        g.add(ex(c), "rdf:type", "rdfs:Class")
        g.add(ex(c), "rdfs:subClassOf", ex("Flight"))
    for name, dom, rng in PROPERTIES:
        g.add(ex(name), "rdf:type", "rdf:Property")
        g.add(ex(name), "rdfs:domain", dom)
        g.add(ex(name), "rdfs:range", rng)


def build_graph(flights, params):
    budget = Decimal(str(params["budget_threshold_eur"]))
    long_min = int(params["long_flight_min"])

    g = Graph()
    add_schema(g)

    dep_counts = Counter(r["from_country"] for r in flights.values())
    busy = {c for c, n in dep_counts.items() if n >= 2}

    airlines, cities, sources = set(), {}, set()

    for fid in sorted(flights):
        r = flights[fid]
        fnode = iri(f"flight/{fid}")

        types = []
        if r["price"] is not None and r["price"] <= budget:
            types.append("BudgetFlight")
        if r["duration"] >= long_min:
            types.append("LongFlight")
        if not types:
            types.append("Flight")
        for t in types:
            g.add(fnode, "rdf:type", ex(t))

        airlines.add(r["airline"])
        cities[r["from_city"]] = r["from_country"]
        cities[r["to_city"]] = r["to_country"]

        g.add(fnode, ex("operatedBy"), iri(f"airline/{r['airline']}"))
        g.add(fnode, ex("departsFrom"), iri(f"city/{r['from_city']}"))
        g.add(fnode, ex("arrivesAt"), iri(f"city/{r['to_city']}"))
        g.add(fnode, ex("departureDate"), lit_typed(r["date"], "xsd:date"))
        g.add(fnode, ex("durationMin"), lit_typed(str(r["duration"]), "xsd:integer"))
        if r["price"] is not None:
            g.add(fnode, ex("priceEur"), lit_typed(format(r["price"], "f"), "xsd:decimal"))
        if r["from_country"] in busy:
            g.add(fnode, ex("fromBusyCountry"), lit_typed("true", "xsd:boolean"))

        note = parse_note(r["note"])
        if "delay" in note:
            stmt = iri(f"stmt/{fid}-delay")
            g.add(stmt, "rdf:type", "rdf:Statement")
            g.add(stmt, "rdf:subject", fnode)
            g.add(stmt, "rdf:predicate", ex("hasDelayMinutes"))
            g.add(stmt, "rdf:object", lit_typed(str(int(note["delay"])), "xsd:integer"))
            if note.get("by"):
                sources.add(note["by"])
                g.add(stmt, ex("reportedBy"), iri(f"source/{note['by']}"))

    for a in sorted(airlines):
        node = iri(f"airline/{a}")
        g.add(node, "rdf:type", ex("Airline"))
        g.add(node, "rdfs:label", lit_str(a, "en"))

    countries = set()
    for city in sorted(cities):
        country = cities[city]
        countries.add(country)
        node = iri(f"city/{city}")
        g.add(node, "rdf:type", ex("City"))
        g.add(node, "rdfs:label", lit_str(city, "en"))
        g.add(node, ex("locatedIn"), iri(f"country/{country}"))

    for c in sorted(countries):
        node = iri(f"country/{c}")
        g.add(node, "rdf:type", ex("Country"))
        g.add(node, "rdfs:label", lit_str(c, "en"))

    for s in sorted(sources):
        g.add(iri(f"source/{s}"), "rdf:type", ex("Source"))

    return g


def main(argv):
    if len(argv) != 4:
        print("Використання: python build_graph.py flights.csv params.json graph.ttl")
        return 1
    csv_path, params_path, out_path = argv[1:]
    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)
    flights = load_flights(csv_path)
    graph = build_graph(flights, params)
    graph.serialize(out_path)
    print(f"{out_path}: {len(flights)} унікальних рейсів, {len(graph.data)} вузлів-субєктів")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
