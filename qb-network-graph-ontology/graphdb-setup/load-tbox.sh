#!/bin/bash
# ============================================================
# load-tbox.sh — Load T-Box ontology into GraphDB qb-ontology
# ============================================================

ENDPOINT="http://localhost:7200/repositories/qb-ontology/statements"
QUERY_ENDPOINT="http://localhost:7200/repositories/qb-ontology"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Loading T-Box Ontology into GraphDB ==="
echo ""

# Load each file in order
FILES=(
  "01-qb-schema.ttl"
  "02-naics-hierarchy.ttl"
  "03-unspsc-hierarchy.ttl"
  "04-geo-hierarchy.ttl"
  "05-cross-taxonomy-links.ttl"
)

for f in "${FILES[@]}"; do
  echo -n "Loading $f ... "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$ENDPOINT" \
    -H "Content-Type: text/turtle" \
    --data-binary "@${DIR}/${f}")
  
  if [ "$HTTP_CODE" = "204" ]; then
    echo "✓"
  else
    echo "✗ (HTTP $HTTP_CODE)"
    echo "  Failed to load $f — check GraphDB logs"
    exit 1
  fi
done

echo ""
echo "=== Verifying Load ==="
echo ""

# Count total triples
echo -n "Total triples (explicit + inferred): "
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['results']['bindings'][0]['count']['value'])" 2>/dev/null \
  || echo "(install python3 to see count)"

# Count NAICS codes
echo -n "NAICS codes: "
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=PREFIX qb: <http://qb.intuit.com/ontology/> SELECT (COUNT(?c) AS ?count) WHERE { ?c a qb:NAICSCode }" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['results']['bindings'][0]['count']['value'])" 2>/dev/null

# Count UNSPSC codes
echo -n "UNSPSC codes: "
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=PREFIX qb: <http://qb.intuit.com/ontology/> SELECT (COUNT(?c) AS ?count) WHERE { ?c a qb:UNSPSCCode }" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['results']['bindings'][0]['count']['value'])" 2>/dev/null

# Count GEO regions
echo -n "GEO regions: "
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=PREFIX qb: <http://qb.intuit.com/ontology/> SELECT (COUNT(?c) AS ?count) WHERE { ?c a qb:GeoRegion }" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['results']['bindings'][0]['count']['value'])" 2>/dev/null

# Count cross-taxonomy links
echo -n "Cross-taxonomy links (skos:related): "
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=PREFIX skos: <http://www.w3.org/2004/02/skos/core#> SELECT (COUNT(*) AS ?count) WHERE { ?a skos:related ?b }" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['results']['bindings'][0]['count']['value'])" 2>/dev/null

echo ""
echo "=== Key Demo Query: Plumbing Contractor ↔ Wholesaler ==="
echo ""

# The money query — does the ontology link NAICS 238220 to 423720?
curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=
PREFIX naics: <http://qb.intuit.com/naics/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?link ?label WHERE {
  naics:238220 skos:related ?link .
  naics:423720 skos:related ?link .
  ?link rdfs:label ?label .
}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
bindings = data['results']['bindings']
if bindings:
    print('  Found shared commodities:')
    for b in bindings:
        print(f'    {b[\"label\"][\"value\"]} ({b[\"link\"][\"value\"].split(\"/\")[-1]})')
    print()
    print('  ✓ Agent will score these as RELATED (0.40) instead of DISQUALIFIED')
else:
    print('  ✗ No cross-taxonomy links found — check 05-cross-taxonomy-links.ttl')
" 2>/dev/null

echo ""
echo "=== Negative Test: Plumbing ↔ Food Service ==="
echo ""

curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=
PREFIX naics: <http://qb.intuit.com/naics/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?link WHERE {
  naics:238220 skos:related ?link .
  naics:722511 skos:related ?link .
}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if not data['results']['bindings']:
    print('  ✓ No shared commodities — correctly unrelated')
else:
    print('  ✗ Unexpected link found')
" 2>/dev/null

echo ""
echo "=== RDFS-Plus Inference Test: subClassOf Transitivity ==="
echo ""

curl -s -G "$QUERY_ENDPOINT" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=
PREFIX naics: <http://qb.intuit.com/naics/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?ancestor ?label WHERE {
  naics:238220 rdfs:subClassOf* ?ancestor .
  ?ancestor rdfs:label ?label .
}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
bindings = data['results']['bindings']
print('  NAICS 238220 hierarchy walk:')
for b in bindings:
    code = b['ancestor']['value'].split('/')[-1]
    label = b['label']['value']
    print(f'    {code}: {label}')
" 2>/dev/null

echo ""
echo "=== Done ==="
