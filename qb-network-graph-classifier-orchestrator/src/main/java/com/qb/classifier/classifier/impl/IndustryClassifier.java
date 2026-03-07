package com.qb.classifier.classifier.impl;

import com.qb.classifier.classifier.Classifier;
import com.qb.classifier.model.EntityConnection;
import java.util.HashMap;
import java.util.Map;

/**
 * Maps free-text category to NAICS code via multi-strategy lookup:
 *   1. Exact match
 *   2. Token-based keyword match
 *   3. Substring containment
 */
public class IndustryClassifier implements Classifier<IndustryClassifier.Result> {

    public record Result(String naicsCode, String naicsSector, String naicsSubsector, String source) {
        public boolean classified() { return naicsCode != null; }
    }

    private static final Result NONE = new Result(null, null, null, "none");

    private static final Map<String, String> CATEGORY_MAP = new HashMap<>();
    private static final Map<String, String> KEYWORD_MAP = new HashMap<>();

    static {
        // Vendor categories
        put("lumber & building materials", "423310");
        put("lumber supply", "423310");
        put("building materials", "423310");
        put("lumber", "423310");
        put("concrete & masonry supply", "423320");
        put("concrete supply", "423320");
        put("masonry supply", "423320");
        put("concrete", "423320");
        put("hardware & fasteners", "423710");
        put("hardware supply", "423710");
        put("hardware store", "423710");
        put("hardware", "423710");
        put("plumbing supply", "423720");
        put("plumbing materials", "423720");
        put("plumbing wholesale", "423720");
        put("electrical supply", "423610");
        put("electrical materials", "423610");
        put("electrical wholesale", "423610");
        put("hvac supply & equipment", "423730");
        put("hvac supply", "423730");
        put("hvac equipment", "423730");
        put("hvac", "423730");
        put("paint & coatings", "424950");
        put("paint supply", "424950");
        put("paint store", "424950");
        put("paint", "424950");
        put("roofing materials", "423330");
        put("roofing supply", "423330");
        put("roofing", "423330");
        put("flooring supply", "423220");
        put("flooring materials", "423220");
        put("flooring", "423220");
        put("equipment rental", "532412");
        put("tool rental", "532412");
        put("construction equipment rental", "532412");
        put("tool & equipment sales", "423810");
        put("tool sales", "423810");
        put("plumbing contractor", "238220");
        put("plumbing services", "238220");
        put("plumbing", "238220");
        put("plumber", "238220");
        put("electrical contractor", "238210");
        put("electrical services", "238210");
        put("electrician", "238210");
        put("hvac contractor", "238220");
        put("hvac services", "238220");
        put("heating and cooling", "238220");
        put("general contractor", "236220");
        put("general contracting", "236220");
        put("commercial building", "236220");
        put("commercial construction", "236220");
        put("construction", "236220");
        put("residential construction", "236118");
        put("home building", "236118");
        put("home builder", "236118");
        put("landscaping", "561730");
        put("lawn and garden", "561730");
        put("lawn care", "561730");
        put("landscape design", "561730");
        put("waste management", "562111");
        put("waste removal", "562111");
        put("dumpster rental", "562111");
        put("debris removal", "562111");
        put("concrete contractor", "238110");
        put("concrete work", "238110");
        put("foundation work", "238110");
        put("insulation", "238310");
        put("insulation contractor", "238310");
        put("drywall", "238310");
        put("drywall contractor", "238310");
        put("cabinet & millwork", "337110");
        put("cabinetry", "337110");
        put("custom cabinets", "337110");
        put("millwork", "337110");
        put("window & door", "423390");
        put("windows and doors", "423390");
        put("safety equipment", "423450");
        put("safety supply", "423450");
        put("ppe supply", "423450");
        put("office supplies", "424120");
        put("office supply", "424120");
        put("fuel & gas", "424710");
        put("fuel supply", "424710");

        // Client categories
        put("homeowner", "531210");
        put("residential", "531210");
        put("residential owner", "531210");
        put("property management", "531311");
        put("property manager", "531311");
        put("apartment management", "531311");
        put("hoa", "813990");
        put("community association", "813990");
        put("homeowners association", "813990");
        put("church", "813110");
        put("religious organization", "813110");
        put("house of worship", "813110");
        put("school", "611110");
        put("education", "611110");
        put("academy", "611110");
        put("municipal", "921110");
        put("city government", "921110");
        put("public works", "921110");
        put("restaurant", "722511");
        put("food service", "722511");
        put("retail", "452210");
        put("retail store", "452210");
        put("interior design", "541410");
        put("interiors", "541410");
        put("real estate", "531210");
        put("real estate investor", "531210");
        put("real estate investment", "531210");
        put("tech company", "541512");
        put("technology", "541512");
        put("software", "541512");
        put("healthcare", "621111");
        put("medical", "621111");
        put("dental", "621210");

        // Keyword → NAICS (for fuzzy matching)
        kw("lumber", "423310"); kw("plywood", "423310"); kw("framing", "423310");
        kw("concrete", "423320"); kw("rebar", "423320"); kw("masonry", "423320");
        kw("hardware", "423710"); kw("fastener", "423710");
        kw("plumbing", "238220"); kw("pipe", "423720"); kw("faucet", "423720");
        kw("electrical", "238210"); kw("wire", "423610"); kw("conduit", "423610");
        kw("hvac", "238220"); kw("ductwork", "423730"); kw("furnace", "423730");
        kw("paint", "424950"); kw("coating", "424950"); kw("stain", "424950");
        kw("roofing", "423330"); kw("shingle", "423330"); kw("gutter", "423330");
        kw("flooring", "423220"); kw("tile", "423220"); kw("carpet", "423220");
        kw("rental", "532412"); kw("excavator", "532412"); kw("scaffold", "532412");
        kw("landscaping", "561730"); kw("lawn", "561730"); kw("irrigation", "561730");
        kw("waste", "562111"); kw("dumpster", "562111"); kw("debris", "562111");
        kw("cabinet", "337110"); kw("millwork", "337110");
        kw("insulation", "238310"); kw("drywall", "238310");
        kw("window", "423390"); kw("door", "423390");
        kw("construction", "236220"); kw("builder", "236118"); kw("contractor", "236220");
        kw("property", "531311"); kw("realty", "531210");
        kw("restaurant", "722511"); kw("church", "813110"); kw("school", "611110");
        kw("medical", "621111"); kw("dental", "621210"); kw("software", "541512");
    }

    private static void put(String cat, String naics) { CATEGORY_MAP.put(cat, naics); }
    private static void kw(String keyword, String naics) { KEYWORD_MAP.put(keyword, naics); }

    @Override
    public Result classify(EntityConnection input) {
        return classifyCategory(input.category());
    }

    @Override
    public String dimensionName() {
        return "industry";
    }

    /** Classify a free-text category into a NAICS code. */
    public static Result classifyCategory(String category) {
        if (category == null || category.isBlank()) return NONE;

        String lower = category.strip().toLowerCase();

        // 1. Exact match
        String code = CATEGORY_MAP.get(lower);
        if (code != null) return result(code, "exact");

        // 2. Token-based keyword match
        String[] tokens = lower.replaceAll("[&-]", " ").split("\\s+");
        for (String token : tokens) {
            code = KEYWORD_MAP.get(token);
            if (code != null) return result(code, "keyword");
        }

        // 3. Substring containment
        for (var entry : CATEGORY_MAP.entrySet()) {
            if (lower.contains(entry.getKey()) || entry.getKey().contains(lower)) {
                return result(entry.getValue(), "substring");
            }
        }

        return NONE;
    }

    private static Result result(String code, String source) {
        return new Result(code, code.substring(0, 2), code.substring(0, 3), source);
    }
}
