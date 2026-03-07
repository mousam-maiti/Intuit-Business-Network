package com.qb.classifier.classifier.impl;

import com.qb.classifier.classifier.Classifier;
import com.qb.classifier.model.EntityConnection;
import java.util.*;
import java.util.regex.Pattern;

/**
 * Extracts structured commodity keywords from free-text fields.
 */
public class CommodityClassifier implements Classifier<CommodityClassifier.Result> {

    public record Result(List<String> topKeywords, List<String> serviceCategories) {}

    private static final Result EMPTY = new Result(List.of(), List.of());

    private static final Map<String, List<String>> CATEGORY_KEYWORDS = Map.ofEntries(
        Map.entry("Materials", List.of(
            "lumber", "plywood", "concrete", "rebar", "shingles", "drywall",
            "pipe", "pvc pipe", "copper fitting", "wire", "conduit",
            "paint", "stain", "tile", "carpet", "vinyl", "hardwood",
            "insulation", "mortar", "blocks", "flashing", "underlayment",
            "framing materials", "osb sheathing", "water heater", "fixtures"
        )),
        Map.entry("Equipment", List.of(
            "excavator", "skid steer", "scaffolding", "generators",
            "power tools", "saws", "drills", "compressors",
            "ductwork", "ac units", "furnaces", "thermostats",
            "breaker panels", "lighting fixtures"
        )),
        Map.entry("Services", List.of(
            "plumbing installation", "pipe repair", "water heater install",
            "wiring", "electrical installation", "panel upgrade",
            "hvac installation", "duct cleaning",
            "roofing installation", "roof repair",
            "flooring installation",
            "excavation", "grading", "demolition",
            "lawn maintenance", "landscape design", "irrigation"
        )),
        Map.entry("Waste", List.of(
            "dumpster", "debris removal", "waste hauling", "roll-off"
        )),
        Map.entry("Supplies", List.of(
            "screws", "nails", "bolts", "anchors", "hand tools",
            "ppe", "safety equipment", "office supplies"
        )),
        Map.entry("General", List.of(
            "plumbing", "electrical", "hvac", "roofing",
            "flooring", "landscaping", "concrete", "lumber", "paint"
        ))
    );

    private static final Map<String, String> KEYWORD_TO_CATEGORY = new HashMap<>();
    static {
        CATEGORY_KEYWORDS.forEach((cat, keywords) ->
            keywords.forEach(kw -> KEYWORD_TO_CATEGORY.put(kw, cat))
        );
    }

    private static final Set<String> ALL_KEYWORDS = KEYWORD_TO_CATEGORY.keySet();
    private static final Pattern SPLIT_RE = Pattern.compile("[,;|/]+|\\band\\b");

    @Override
    public Result classify(EntityConnection input) {
        return extract(input.commodity(), input.category(), input.displayName());
    }

    @Override
    public String dimensionName() {
        return "commodity";
    }

    /** Extract commodity keywords from entity connection fields. */
    public static Result extract(String commodity, String category, String displayName) {
        Set<String> foundKeywords = new LinkedHashSet<>();
        Set<String> foundCategories = new LinkedHashSet<>();

        // 1. Parse explicit commodity field (strongest signal)
        if (commodity != null && !commodity.isBlank()) {
            extractFromText(commodity, foundKeywords, foundCategories);
        }

        // 2. Parse category field (medium signal)
        if (category != null && !category.isBlank()) {
            extractFromText(category, foundKeywords, foundCategories);
        }

        // 3. Parse display name (weak signal)
        if (displayName != null && !displayName.isBlank()) {
            String lower = displayName.toLowerCase();
            for (String kw : List.of("plumbing", "electrical", "hvac", "roofing",
                    "flooring", "landscaping", "concrete", "lumber", "paint")) {
                if (lower.contains(kw)) {
                    foundKeywords.add(kw);
                    String cat = KEYWORD_TO_CATEGORY.get(kw);
                    if (cat != null) foundCategories.add(cat);
                }
            }
        }

        if (foundKeywords.isEmpty()) return EMPTY;

        return new Result(
            foundKeywords.stream().limit(5).toList(),
            foundCategories.stream().filter(c -> !"General".equals(c)).toList()
        );
    }

    private static void extractFromText(String text, Set<String> keywords, Set<String> categories) {
        String lower = text.strip().toLowerCase();
        String[] segments = SPLIT_RE.split(lower);

        for (String segment : segments) {
            String trimmed = segment.strip();
            if (trimmed.isEmpty()) continue;

            if (ALL_KEYWORDS.contains(trimmed)) {
                keywords.add(trimmed);
                String cat = KEYWORD_TO_CATEGORY.get(trimmed);
                if (cat != null) categories.add(cat);
                continue;
            }

            for (String kw : ALL_KEYWORDS) {
                if (trimmed.contains(kw)) {
                    keywords.add(kw);
                    String cat = KEYWORD_TO_CATEGORY.get(kw);
                    if (cat != null) categories.add(cat);
                }
            }

            if (keywords.isEmpty() || keywords.stream().noneMatch(trimmed::contains)) {
                String cleaned = trimmed.replaceAll("[^a-z0-9 ]", "").replaceAll("\\s{2,}", " ").strip();
                if (!cleaned.isEmpty() && cleaned.length() > 2) {
                    keywords.add(cleaned);
                }
            }
        }
    }
}
