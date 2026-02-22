package com.qb.classifier.classify;

import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Normalizes raw display_name into identity classification fields.
 *
 * Steps:
 *   1. Detect legal suffix (LLC, INC, CORP, etc.)
 *   2. Strip suffix + punctuation
 *   3. Uppercase
 *   4. Tokenize and filter noise
 */
public final class NameNormalizer {

    /** Legal suffixes sorted longest-first to avoid partial matches. */
    private static final List<String> LEGAL_SUFFIXES = List.of(
        "LIMITED LIABILITY COMPANY", "LIMITED LIABILITY CO",
        "INCORPORATED", "CORPORATION", "COMPANY",
        "LLC", "INC", "CORP", "CO", "LTD", "LP", "LLP",
        "PLLC", "PC", "PA", "DBA"
    );

    private static final Pattern SUFFIX_RE;
    static {
        String joined = LEGAL_SUFFIXES.stream()
            .map(Pattern::quote)
            .collect(Collectors.joining("|"));
        SUFFIX_RE = Pattern.compile(
            "\\b(?:" + joined + ")\\.?\\s*$",
            Pattern.CASE_INSENSITIVE
        );
    }

    /** Intra-word punctuation to remove entirely (apostrophes, etc.). */
    private static final Pattern GLUE_PUNCT_RE = Pattern.compile("['\u2019]+");
    /** Word-separating punctuation and symbols to replace with spaces. */
    private static final Pattern SEP_PUNCT_RE = Pattern.compile("[\".,()&/\\\\-]+");
    private static final Pattern MULTI_SPACE = Pattern.compile("\\s{2,}");
    private static final Set<String> NOISE = Set.of("THE", "AND", "OF", "A", "AN");

    private NameNormalizer() {}

    public record Result(
        String normalizedName,
        String nameFirstToken,
        List<String> nameTokens,
        String legalSuffix
    ) {}

    /**
     * Normalize a raw display name.
     */
    public static Result normalize(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            return new Result("", "", List.of(), null);
        }

        String raw = displayName.strip();

        // 1. Detect legal suffix
        Matcher m = SUFFIX_RE.matcher(raw.toUpperCase());
        String suffix = m.find() ? m.group().strip().replaceAll("\\.$", "") : null;

        // 2. Uppercase
        String upper = raw.toUpperCase();

        // 3. Strip trailing suffixes (loop to handle stacked suffixes like "Co Inc.")
        String prev;
        do {
            prev = upper;
            upper = SUFFIX_RE.matcher(upper).replaceAll("").strip();
        } while (!upper.equals(prev));

        // 4. Remove punctuation: strip apostrophes entirely, replace separators with space
        String clean = GLUE_PUNCT_RE.matcher(upper).replaceAll("");
        clean = SEP_PUNCT_RE.matcher(clean).replaceAll(" ");
        clean = MULTI_SPACE.matcher(clean).replaceAll(" ").strip();

        // 5. Tokenize
        String[] allTokens = clean.isEmpty() ? new String[0] : clean.split("\\s+");

        // 6. Filter noise
        List<String> meaningful = java.util.Arrays.stream(allTokens)
            .filter(t -> !NOISE.contains(t) && t.length() > 1)
            .toList();

        List<String> finalTokens = meaningful.isEmpty()
            ? java.util.Arrays.stream(allTokens)
                .filter(t -> !NOISE.contains(t))
                .toList()
            : meaningful;

        return new Result(
            clean,
            finalTokens.isEmpty() ? "" : finalTokens.get(0),
            finalTokens,
            suffix
        );
    }
}
