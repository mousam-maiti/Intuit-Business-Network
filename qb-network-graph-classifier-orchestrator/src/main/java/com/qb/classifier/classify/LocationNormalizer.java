package com.qb.classifier.classify;

/**
 * Normalizes location fields into the agent's LocationDimension.
 *
 * - city → UPPERCASE
 * - state → UPPERCASE 2-letter
 * - zip → zip5 (full) + zip3 (prefix)
 */
public final class LocationNormalizer {

    public record Result(String state, String cityNorm, String zip3, String zip5) {}

    private static final Result EMPTY = new Result(null, null, null, null);

    private LocationNormalizer() {}

    public static Result normalize(String city, String state, String zip) {
        String normState = (state != null && !state.isBlank())
            ? state.strip().toUpperCase() : null;

        String normCity = (city != null && !city.isBlank())
            ? city.strip().toUpperCase() : null;

        String zip5 = null;
        String zip3 = null;
        if (zip != null && !zip.isBlank()) {
            // Handle "78745" or "78745-1234"
            String clean = zip.strip().replaceAll("[^0-9]", "");
            if (clean.length() >= 5) {
                zip5 = clean.substring(0, 5);
                zip3 = clean.substring(0, 3);
            } else if (clean.length() >= 3) {
                zip3 = clean.substring(0, 3);
            }
        }

        if (normState == null && normCity == null && zip3 == null) return EMPTY;

        return new Result(normState, normCity, zip3, zip5);
    }
}
