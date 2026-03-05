package com.qb.classifier.classifier.impl;

import com.qb.classifier.classifier.Classifier;
import com.qb.classifier.model.EntityConnection;
import java.util.regex.Pattern;

/**
 * Normalizes identity fields: EIN, phone, email.
 */
public class IdentityClassifier implements Classifier<IdentityClassifier.Result> {

    public record Result(String einClean, String phoneDigits, String email, String emailDomain) {}

    private static final Pattern NON_DIGIT = Pattern.compile("[^0-9]");
    private static final Pattern EIN_VALID = Pattern.compile("^\\d{9}$");
    private static final Pattern PHONE_VALID = Pattern.compile("^\\d{10}$");

    private static final Result EMPTY = new Result(null, null, null, null);

    @Override
    public Result classify(EntityConnection input) {
        return new Result(
            cleanEin(input.ein()),
            cleanPhone(input.phone()),
            cleanEmail(input.email()),
            emailDomain(input.email())
        );
    }

    @Override
    public String dimensionName() {
        return "identity";
    }

    // ── Static helpers (kept public for direct use in tests) ──

    public static String cleanEin(String ein) {
        if (ein == null || ein.isBlank()) return null;
        String digits = NON_DIGIT.matcher(ein).replaceAll("");
        return EIN_VALID.matcher(digits).matches() ? digits : null;
    }

    public static String cleanPhone(String phone) {
        if (phone == null || phone.isBlank()) return null;
        String digits = NON_DIGIT.matcher(phone).replaceAll("");
        if (digits.length() == 11 && digits.startsWith("1")) {
            digits = digits.substring(1);
        }
        return PHONE_VALID.matcher(digits).matches() ? digits : null;
    }

    public static String cleanEmail(String email) {
        if (email == null || email.isBlank()) return null;
        String lower = email.strip().toLowerCase();
        return lower.contains("@") ? lower : null;
    }

    public static String emailDomain(String email) {
        String clean = cleanEmail(email);
        if (clean == null) return null;
        int at = clean.indexOf('@');
        return at >= 0 ? clean.substring(at + 1) : null;
    }
}
