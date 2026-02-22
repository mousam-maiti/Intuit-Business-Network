package com.qb.classifier.classify;

import java.util.regex.Pattern;

/**
 * Normalizes identity fields: EIN, phone, email.
 *
 * - EIN: strip dashes, validate 9 digits
 * - Phone: extract 10 digits
 * - Email: lowercase, extract domain
 */
public final class IdentityClassifier {

    private static final Pattern NON_DIGIT = Pattern.compile("[^0-9]");
    private static final Pattern EIN_VALID = Pattern.compile("^\\d{9}$");
    private static final Pattern PHONE_VALID = Pattern.compile("^\\d{10}$");

    private IdentityClassifier() {}

    /** Strip dashes/spaces, return 9-digit EIN or null. */
    public static String cleanEin(String ein) {
        if (ein == null || ein.isBlank()) return null;
        String digits = NON_DIGIT.matcher(ein).replaceAll("");
        return EIN_VALID.matcher(digits).matches() ? digits : null;
    }

    /** Extract 10 digits from phone or null. */
    public static String cleanPhone(String phone) {
        if (phone == null || phone.isBlank()) return null;
        String digits = NON_DIGIT.matcher(phone).replaceAll("");
        // Strip leading 1 for US numbers
        if (digits.length() == 11 && digits.startsWith("1")) {
            digits = digits.substring(1);
        }
        return PHONE_VALID.matcher(digits).matches() ? digits : null;
    }

    /** Lowercase email, or null. */
    public static String cleanEmail(String email) {
        if (email == null || email.isBlank()) return null;
        String lower = email.strip().toLowerCase();
        return lower.contains("@") ? lower : null;
    }

    /** Extract domain from email ("bob@acme.com" → "acme.com"). */
    public static String emailDomain(String email) {
        String clean = cleanEmail(email);
        if (clean == null) return null;
        int at = clean.indexOf('@');
        return at >= 0 ? clean.substring(at + 1) : null;
    }
}
