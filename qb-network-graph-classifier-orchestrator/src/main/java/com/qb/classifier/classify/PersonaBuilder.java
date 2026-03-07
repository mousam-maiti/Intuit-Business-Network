package com.qb.classifier.classify;

import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.ClassifiedPersona.*;
import com.qb.classifier.model.EntityConnection;

/**
 * Assembles a ClassifiedPersona from a raw EntityConnection row.
 *
 * Orchestrates all classifiers:
 *   NameNormalizer      → identity.normalized_name, name_tokens, legal_suffix
 *   IdentityClassifier  → identity.ein_clean, phone_digits, email_domain
 *   IndustryClassifier  → industry.naics_code/sector/subsector
 *   CommodityExtractor  → commodity.top_keywords, service_categories
 *   LocationNormalizer   → location.city_norm, state, zip3/zip5
 *   BehavioralClassifier → behavioral.volume_bracket, avg_transaction
 *
 * Also computes sparsity scores per dimension (0-5 scale).
 */
public final class PersonaBuilder {

    private PersonaBuilder() {}

    /**
     * Build a fully classified persona from a raw entity_connections row.
     */
    public static ClassifiedPersona build(EntityConnection conn) {

        // ── Identity ──
        NameNormalizer.Result name = NameNormalizer.normalize(conn.displayName());
        String einClean = IdentityClassifier.cleanEin(conn.ein());
        String phoneDigits = IdentityClassifier.cleanPhone(conn.phone());
        String email = IdentityClassifier.cleanEmail(conn.email());
        String emailDomain = IdentityClassifier.emailDomain(conn.email());

        IdentityDimension identity = new IdentityDimension(
            name.normalizedName(),
            name.nameFirstToken(),
            name.nameTokens(),
            name.legalSuffix(),
            einClean,
            phoneDigits,
            email,
            emailDomain
        );

        // ── Industry ──
        IndustryClassifier.Result naics = IndustryClassifier.classify(conn.category());
        CommodityExtractor.Result commodities = CommodityExtractor.extract(
            conn.commodity(), conn.category(), conn.displayName()
        );

        IndustryDimension industry = new IndustryDimension(
            naics.naicsCode(),
            naics.naicsSector(),
            naics.naicsSubsector(),
            conn.category(),
            commodities.topKeywords()
        );

        // ── Location ──
        LocationNormalizer.Result loc = LocationNormalizer.normalize(
            conn.city(), conn.state(), conn.zip()
        );

        LocationDimension location = new LocationDimension(
            loc.state(),
            loc.cityNorm(),
            loc.zip3(),
            loc.zip5()
        );

        // ── Commodity ──
        CommodityDimension commodity = new CommodityDimension(
            commodities.topKeywords(),
            commodities.serviceCategories()
        );

        // ── Behavioral ──
        BehavioralClassifier.Result behav = BehavioralClassifier.classify(
            conn.totalVolume(), conn.transactionCount()
        );

        BehavioralDimension behavioral = new BehavioralDimension(
            behav.volumeBracket(),
            behav.avgTransaction(),
            behav.transactionCount(),
            conn.paymentTerms()
        );

        // ── Sparsity ──
        SparsityScores sparsity = computeSparsity(identity, industry, location, commodity, behavioral);

        return new ClassifiedPersona(identity, industry, location, commodity, behavioral, sparsity);
    }

    /**
     * Compute sparsity scores per dimension (0-5 scale).
     * Higher = more data available. Used by the agent to weight dimensions.
     */
    private static SparsityScores computeSparsity(
            IdentityDimension id,
            IndustryDimension ind,
            LocationDimension loc,
            CommodityDimension comm,
            BehavioralDimension beh) {

        // Identity: name(1) + ein(1) + phone(1) + email(1) + legal_suffix(1) = max 5
        int identityScore = 0;
        if (!id.normalizedName().isBlank()) identityScore++;
        if (id.einClean() != null) identityScore++;
        if (id.phoneDigits() != null) identityScore++;
        if (id.email() != null) identityScore++;
        if (id.legalSuffix() != null) identityScore++;

        // Industry: naics_code(2) + commodity_keywords(count, max 3) = max 5
        int industryScore = 0;
        if (ind.naicsCode() != null) industryScore += 2;
        industryScore += Math.min(ind.commodityKeywords().size(), 3);

        // Location: state(1) + city(1) + zip5(2) or zip3(1) = max 4
        int locationScore = 0;
        if (loc.state() != null) locationScore++;
        if (loc.cityNorm() != null) locationScore++;
        if (loc.zip5() != null) locationScore += 2;
        else if (loc.zip3() != null) locationScore++;

        // Commodity: top_keywords(count, max 4) + service_categories(1) = max 5
        int commodityScore = 0;
        commodityScore += Math.min(comm.topKeywords().size(), 4);
        if (!comm.serviceCategories().isEmpty()) commodityScore++;

        // Behavioral: volume_bracket(1) + avg_txn(1) + count(1) + terms(1) = max 4
        int behavioralScore = 0;
        if (beh.volumeBracket() != null) behavioralScore++;
        if (beh.avgTransaction() != null) behavioralScore++;
        if (beh.transactionCount() != null) behavioralScore++;
        if (beh.paymentTerms() != null) behavioralScore++;

        return new SparsityScores(
            Math.min(identityScore, 5),
            Math.min(industryScore, 5),
            Math.min(locationScore, 5),
            Math.min(commodityScore, 5),
            Math.min(behavioralScore, 5)
        );
    }
}
