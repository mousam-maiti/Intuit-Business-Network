package com.qb.classifier.classify;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Classifies behavioral signals from transaction aggregates.
 *
 * Volume brackets (annualized):
 *   VERY_LOW  → < $10,000
 *   LOW       → $10,000 - $50,000
 *   MEDIUM    → $50,000 - $250,000
 *   HIGH      → $250,000 - $1,000,000
 *   VERY_HIGH → > $1,000,000
 */
public final class BehavioralClassifier {

    public record Result(String volumeBracket, Double avgTransaction, Integer transactionCount) {}

    private static final Result EMPTY = new Result(null, null, null);

    private BehavioralClassifier() {}

    public static Result classify(BigDecimal totalVolume, Long transactionCount) {
        if (totalVolume == null || transactionCount == null || transactionCount == 0) {
            return EMPTY;
        }

        String bracket = bracket(totalVolume);
        double avg = totalVolume
            .divide(BigDecimal.valueOf(transactionCount), 2, RoundingMode.HALF_UP)
            .doubleValue();

        return new Result(bracket, avg, transactionCount.intValue());
    }

    private static String bracket(BigDecimal volume) {
        double v = volume.doubleValue();
        if (v < 10_000)       return "VERY_LOW";
        if (v < 50_000)       return "LOW";
        if (v < 250_000)      return "MEDIUM";
        if (v < 1_000_000)    return "HIGH";
        return "VERY_HIGH";
    }
}
