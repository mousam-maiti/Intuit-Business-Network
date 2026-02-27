#!/bin/bash
# ============================================================
# test-graphdb.sh — Validate all SPARQL patterns the agent uses
#
# Covers query patterns for all 4 knowledge_graph MCP tools:
#   - query_ontology (T-Box reads)
#   - check_shared_context (A-Box + T-Box reads)
#   - write_entity_triples (A-Box writes)
#   - write_merge_redirect (A-Box writes + owl:sameAs)
# ============================================================

QUERY="http://localhost:7200/repositories/qb-ontology"
UPDATE="http://localhost:7200/repositories/qb-ontology/statements"
PASS=0
FAIL=0

run_query() {
  local desc="$1"
  local sparql="$2"
  local expect="$3"  # "nonempty" | "empty" | number | string to grep

  echo -n "  $desc ... "
  RESULT=$(curl -s -G "$QUERY" \
    -H "Accept: application/sparql-results+json" \
    --data-urlencode "query=$sparql")

  BINDINGS=$(echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    b = data['results']['bindings']
    print(len(b))
    for row in b:
        vals = [v['value'] for v in row.values()]
        print('|'.join(vals))
except: print('ERROR')
" 2>/dev/null)

  COUNT=$(echo "$BINDINGS" | head -1)

  if [ "$expect" = "nonempty" ]; then
    if [ "$COUNT" != "0" ] && [ "$COUNT" != "ERROR" ]; then
      echo "✓ ($COUNT results)"
      PASS=$((PASS+1))
    else
      echo "✗ (expected results, got $COUNT)"
      FAIL=$((FAIL+1))
    fi
  elif [ "$expect" = "empty" ]; then
    if [ "$COUNT" = "0" ]; then
      echo "✓ (0 results — correct)"
      PASS=$((PASS+1))
    else
      echo "✗ (expected 0, got $COUNT)"
      FAIL=$((FAIL+1))
    fi
  elif [[ "$expect" =~ ^[0-9]+$ ]]; then
    if [ "$COUNT" = "$expect" ]; then
      echo "✓ ($COUNT results)"
      PASS=$((PASS+1))
    else
      echo "✗ (expected $expect, got $COUNT)"
      FAIL=$((FAIL+1))
    fi
  else
    # grep for string in output
    if echo "$BINDINGS" | grep -qi "$expect"; then
      echo "✓ (found '$expect')"
      PASS=$((PASS+1))
    else
      echo "✗ (expected '$expect' in output)"
      echo "    Got: $(echo "$BINDINGS" | tail -3)"
      FAIL=$((FAIL+1))
    fi
  fi
}

run_update() {
  local desc="$1"
  local sparql="$2"

  echo -n "  $desc ... "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$UPDATE" \
    -H "Content-Type: application/sparql-update" \
    -d "$sparql")

  if [ "$HTTP_CODE" = "204" ]; then
    echo "✓"
    PASS=$((PASS+1))
  else
    echo "✗ (HTTP $HTTP_CODE)"
    FAIL=$((FAIL+1))
  fi
}

# ============================================================
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  GraphDB T-Box + A-Box Integration Tests            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ============================================================
echo "── 1. SCHEMA VERIFICATION ──"
echo ""

run_query "Business class exists" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?c WHERE { qb:Business a ?c }" \
  "nonempty"

run_query "GoldenRecord subClassOf Business" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?sub WHERE { qb:GoldenRecord rdfs:subClassOf qb:Business }" \
  "nonempty"

run_query "PhantomEntity subClassOf Business" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?sub WHERE { qb:PhantomEntity rdfs:subClassOf qb:Business }" \
  "nonempty"

run_query "transactsWith is SymmetricProperty" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX owl: <http://www.w3.org/2002/07/owl#>
   SELECT ?p WHERE { qb:transactsWith a owl:SymmetricProperty }" \
  "nonempty"

run_query "All entity properties defined (ein, email, phone, contactName, zipCode, paymentTerms)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?p WHERE {
     ?p rdfs:domain qb:Business .
     FILTER(?p IN (qb:ein, qb:email, qb:phone, qb:contactName, qb:zipCode, qb:paymentTerms))
   }" \
  "6"

echo ""

# ============================================================
echo "── 2. NAICS HIERARCHY (query_ontology patterns) ──"
echo ""

run_query "NAICS 238220 hierarchy walk (rdfs:subClassOf*)" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?ancestor ?label WHERE {
     naics:238220 rdfs:subClassOf* ?ancestor .
     ?ancestor rdfs:label ?label .
   }" \
  "4"

run_query "NAICS 238220 traces to sector 23 (Construction)" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?label WHERE {
     naics:238220 rdfs:subClassOf* naics:23 .
     naics:23 rdfs:label ?label .
   }" \
  "Construction"

run_query "NAICS 423720 traces to sector 42 (Wholesale)" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?label WHERE {
     naics:423720 rdfs:subClassOf* naics:42 .
     naics:42 rdfs:label ?label .
   }" \
  "Wholesale"

run_query "Lowest common ancestor of 238220 vs 423720 (should be none)" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?lca WHERE {
     naics:238220 rdfs:subClassOf* ?lca .
     naics:423720 rdfs:subClassOf* ?lca .
     ?lca a qb:NAICSCode .
   }" \
  "empty"

run_query "Lowest common ancestor of 238220 vs 238210 (should be 2382)" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?lca ?label WHERE {
     naics:238220 rdfs:subClassOf* ?lca .
     naics:238210 rdfs:subClassOf* ?lca .
     ?lca a qb:NAICSCode .
     ?lca rdfs:label ?label .
   } ORDER BY DESC(strlen(str(?lca))) LIMIT 1" \
  "Building Equipment"

echo ""

# ============================================================
echo "── 3. UNSPSC HIERARCHY ──"
echo ""

run_query "UNSPSC 72151500 hierarchy walk" \
  "PREFIX unspsc: <http://qb.intuit.com/unspsc/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?ancestor ?label WHERE {
     unspsc:72151500 rdfs:subClassOf* ?ancestor .
     ?ancestor rdfs:label ?label .
   }" \
  "nonempty"

run_query "Pipe Fittings (40141600) has children (PVC, Copper)" \
  "PREFIX unspsc: <http://qb.intuit.com/unspsc/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?child ?label WHERE {
     ?child rdfs:subClassOf unspsc:40141600 .
     ?child rdfs:label ?label .
   }" \
  "2"

echo ""

# ============================================================
echo "── 4. GEO HIERARCHY ──"
echo ""

run_query "Austin is within Texas" \
  "PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?state WHERE {
     geo:austin qb:withinState ?state .
   }" \
  "texas"

run_query "Austin is within Austin metro" \
  "PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?metro WHERE {
     geo:austin qb:withinMetro ?metro .
   }" \
  "austin-metro"

run_query "All cities in Texas (via withinState)" \
  "PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   SELECT ?city ?label WHERE {
     ?city qb:withinState geo:texas .
     ?city a qb:City .
     ?city rdfs:label ?label .
   }" \
  "nonempty"

run_query "GEO containment: cities in Austin metro" \
  "PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?city ?label WHERE {
     ?city qb:withinMetro geo:austin-metro .
     ?city rdfs:label ?label .
   }" \
  "4"

echo ""

# ============================================================
echo "── 5. CROSS-TAXONOMY LINKS (the money queries) ──"
echo ""

run_query "Plumbing contractor (238220) ↔ Wholesaler (423720) shared commodities" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?link ?label WHERE {
     naics:238220 skos:related ?link .
     naics:423720 skos:related ?link .
     ?link rdfs:label ?label .
   }" \
  "4"

run_query "Plumbing (238220) ↔ Food Service (722511) — should be unrelated" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
   SELECT ?link WHERE {
     naics:238220 skos:related ?link .
     naics:722511 skos:related ?link .
   }" \
  "empty"

run_query "Auto repair (811111) ↔ Plumbing (238220) — should be unrelated" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
   SELECT ?link WHERE {
     naics:811111 skos:related ?link .
     naics:238220 skos:related ?link .
   }" \
  "empty"

run_query "Electrical (238210) ↔ Plumbing (238220) intra-NAICS relatedness" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
   SELECT ?x WHERE {
     naics:238210 skos:related naics:238220 .
     BIND(1 AS ?x)
   }" \
  "nonempty"

run_query "Residential builder (236110) related to all specialty trades" \
  "PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
   SELECT ?trade WHERE {
     naics:236110 skos:related ?trade .
     FILTER(STRSTARTS(STR(?trade), 'http://qb.intuit.com/naics/238'))
   }" \
  "4"

echo ""

# ============================================================
echo "── 6. A-BOX WRITE: write_entity_triples ──"
echo ""

run_update "Create test entity (Bob's Plumbing)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX unspsc: <http://qb.intuit.com/unspsc/>
   PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
   INSERT DATA {
     entity:test-G001 a qb:GoldenRecord .
     entity:test-G001 qb:canonicalName \"Bob's Plumbing LLC\" .
     entity:test-G001 qb:ein \"74-8841234\" .
     entity:test-G001 qb:email \"bob@bobsplumbing.com\" .
     entity:test-G001 qb:contactName \"Bob Smith\" .
     entity:test-G001 qb:phone \"5124551234\" .
     entity:test-G001 qb:streetAddress \"123 Main St\" .
     entity:test-G001 qb:zipCode \"78701\" .
     entity:test-G001 qb:paymentTerms \"Net 30\" .
     entity:test-G001 qb:nameVariant \"Bobs Plumbing\" .
     entity:test-G001 qb:nameVariant \"BP Supply\" .
     entity:test-G001 qb:operatesIn naics:238220 .
     entity:test-G001 qb:provides unspsc:72151500 .
     entity:test-G001 qb:provides unspsc:40141600 .
     entity:test-G001 qb:locatedIn geo:austin .
     entity:test-G001 qb:entityStatus \"ACTIVE\" .
     entity:test-G001 qb:entityType \"QB_USER\" .
     entity:test-G001 qb:confidence \"0.92\"^^xsd:float .
     entity:test-G001 qb:transactionVolume \"125000\"^^xsd:decimal .
   }"

run_update "Create test entity (Acme Construction)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   INSERT DATA {
     entity:test-G002 a qb:GoldenRecord .
     entity:test-G002 qb:canonicalName \"Acme Construction Inc\" .
     entity:test-G002 qb:operatesIn naics:236110 .
     entity:test-G002 qb:locatedIn geo:austin .
     entity:test-G002 qb:entityStatus \"ACTIVE\" .
   }"

run_update "Create test entity (FastPipe Wholesale)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX unspsc: <http://qb.intuit.com/unspsc/>
   PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   INSERT DATA {
     entity:test-G003 a qb:GoldenRecord .
     entity:test-G003 qb:canonicalName \"FastPipe Supply Co\" .
     entity:test-G003 qb:operatesIn naics:423720 .
     entity:test-G003 qb:provides unspsc:40141600 .
     entity:test-G003 qb:provides unspsc:40141700 .
     entity:test-G003 qb:locatedIn geo:round-rock .
     entity:test-G003 qb:entityStatus \"ACTIVE\" .
   }"

run_update "Create edges (transactsWith)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   INSERT DATA {
     entity:test-G002 qb:transactsWith entity:test-G001 .
     entity:test-G001 qb:transactsWith entity:test-G003 .
     entity:test-G002 qb:transactsWith entity:test-G003 .
   }"

echo ""

# ============================================================
echo "── 7. A-BOX READ: Verify entities written ──"
echo ""

run_query "Read Bob's Plumbing — all attributes" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?p ?o WHERE {
     entity:test-G001 ?p ?o .
     FILTER(STRSTARTS(STR(?p), 'http://qb.intuit.com/'))
   }" \
  "nonempty"

run_query "Bob's Plumbing has 2 name variants" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?v WHERE {
     entity:test-G001 qb:nameVariant ?v .
   }" \
  "2"

run_query "Bob's Plumbing provides 2 UNSPSC codes" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?code WHERE {
     entity:test-G001 qb:provides ?code .
   }" \
  "2"

run_query "Bob's EIN is 74-8841234" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?ein WHERE {
     entity:test-G001 qb:ein ?ein .
   }" \
  "74-8841234"

echo ""

# ============================================================
echo "── 8. SYMMETRIC PROPERTY: transactsWith ──"
echo ""

run_query "G002 transactsWith G001 (explicit)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?x WHERE {
     entity:test-G002 qb:transactsWith entity:test-G001 .
     BIND(1 AS ?x)
   }" \
  "nonempty"

run_query "G001 transactsWith G002 (inferred via SymmetricProperty)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?x WHERE {
     entity:test-G001 qb:transactsWith entity:test-G002 .
     BIND(1 AS ?x)
   }" \
  "nonempty"

run_query "Bob's Plumbing has 2 transaction partners" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?partner WHERE {
     entity:test-G001 qb:transactsWith ?partner .
   }" \
  "2"

echo ""

# ============================================================
echo "── 9. CHECK_SHARED_CONTEXT PATTERN ──"
echo ""

run_query "Shared neighbors: G001 and G003 both transact with G002" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?shared ?name WHERE {
     entity:test-G001 qb:transactsWith ?shared .
     entity:test-G003 qb:transactsWith ?shared .
     ?shared qb:canonicalName ?name .
   }" \
  "Acme"

run_query "Industry coherence: shared neighbor's NAICS in construction hierarchy" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?shared ?naics ?sector WHERE {
     entity:test-G001 qb:transactsWith ?shared .
     entity:test-G003 qb:transactsWith ?shared .
     ?shared qb:operatesIn ?naics .
     ?naics rdfs:subClassOf* ?sector .
     ?sector rdfs:label ?sectorLabel .
     FILTER(?sector = naics:23)
   }" \
  "nonempty"

echo ""

# ============================================================
echo "── 10. COMPLEX QUERY: Find all entities in construction-related industries near Austin ──"
echo ""

run_query "Entities in construction (NAICS 23+) within Austin metro" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?entity ?name ?naics ?city WHERE {
     ?entity a qb:GoldenRecord .
     ?entity qb:canonicalName ?name .
     ?entity qb:operatesIn ?naics .
     ?naics rdfs:subClassOf* naics:23 .
     ?entity qb:locatedIn ?city .
     ?city qb:withinMetro geo:austin-metro .
   }" \
  "nonempty"

echo ""

# ============================================================
echo "── 11. WRITE_MERGE_REDIRECT PATTERN ──"
echo ""

run_update "Create duplicate entity to merge (BP Supply LLC)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX naics: <http://qb.intuit.com/naics/>
   PREFIX geo: <http://qb.intuit.com/geo/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   INSERT DATA {
     entity:test-G004 a qb:GoldenRecord .
     entity:test-G004 qb:canonicalName \"BP Supply LLC\" .
     entity:test-G004 qb:operatesIn naics:238220 .
     entity:test-G004 qb:locatedIn geo:austin .
     entity:test-G004 qb:entityStatus \"ACTIVE\" .
     entity:test-G004 qb:transactsWith entity:test-G002 .
   }"

run_update "Merge redirect: migrate G004 edges to G001 (survivor)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE { ?x qb:transactsWith entity:test-G004 }
   INSERT { ?x qb:transactsWith entity:test-G001 }
   WHERE  { ?x qb:transactsWith entity:test-G004 }"

run_update "Add owl:sameAs redirect" \
  "PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX entity: <http://qb.intuit.com/entity/>
   INSERT DATA {
     entity:test-G004 owl:sameAs entity:test-G001 .
   }"

run_update "Mark absorbed entity as MERGED" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE { entity:test-G004 qb:entityStatus ?old }
   INSERT { entity:test-G004 qb:entityStatus \"MERGED\" }
   WHERE  { entity:test-G004 qb:entityStatus ?old }"

run_query "owl:sameAs resolves: querying G004 finds G001" \
  "PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?name WHERE {
     entity:test-G004 owl:sameAs ?survivor .
     ?survivor qb:canonicalName ?name .
   }" \
  "Bob"

run_query "owl:sameAs inference: G004 inherits G001 edges (expected)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?partner WHERE {
     entity:test-G004 qb:transactsWith ?partner .
   }" \
  "nonempty"

run_query "G004 explicit edges were migrated (no direct G004 triples in explicit graph)" \
  "PREFIX qb: <http://qb.intuit.com/ontology/>
   PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?partner WHERE {
     GRAPH <http://www.ontotext.com/explicit> {
       ?partner qb:transactsWith entity:test-G004 .
     }
   }" \
  "empty"

echo ""

# ============================================================
echo "── 12. CLEANUP: Remove test A-Box data ──"
echo ""

run_update "Remove owl:sameAs redirect first" \
  "PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { entity:test-G004 owl:sameAs ?o }"

run_update "Delete test entity G001" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { entity:test-G001 ?p ?o }"

run_update "Delete test entity G002" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { entity:test-G002 ?p ?o }"

run_update "Delete test entity G003" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { entity:test-G003 ?p ?o }"

run_update "Delete test entity G004" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { entity:test-G004 ?p ?o }"

run_update "Delete reverse edges referencing test entities" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   DELETE WHERE { ?s ?p ?o .
     FILTER(STRSTARTS(STR(?o), 'http://qb.intuit.com/entity/test-'))
   }"

run_query "Verify cleanup — no test entities remain" \
  "PREFIX entity: <http://qb.intuit.com/entity/>
   SELECT ?s WHERE {
     ?s ?p ?o .
     FILTER(STRSTARTS(STR(?s), 'http://qb.intuit.com/entity/test-'))
   }" \
  "empty"

echo ""

# ============================================================
echo "════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
