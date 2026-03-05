package com.qb.classifier.classifier;

import com.qb.classifier.classifier.impl.*;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.ClassifiedPersona.*;
import com.qb.classifier.model.EntityConnection;
/**
 * Assembles a ClassifiedPersona from a raw EntityConnection row.
 *
 * Orchestrates all dimension classifiers via constructor injection.
 * Open for extension — add a new classifier @Component and inject here.
 */
public class PersonaBuilder {

    private final NameClassifier nameClassifier;
    private final IdentityClassifier identityClassifier;
    private final IndustryClassifier industryClassifier;
    private final LocationClassifier locationClassifier;
    private final CommodityClassifier commodityClassifier;
    private final BehavioralClassifier behavioralClassifier;

    public PersonaBuilder(
            NameClassifier nameClassifier,
            IdentityClassifier identityClassifier,
            IndustryClassifier industryClassifier,
            LocationClassifier locationClassifier,
            CommodityClassifier commodityClassifier,
            BehavioralClassifier behavioralClassifier) {
        this.nameClassifier = nameClassifier;
        this.identityClassifier = identityClassifier;
        this.industryClassifier = industryClassifier;
        this.locationClassifier = locationClassifier;
        this.commodityClassifier = commodityClassifier;
        this.behavioralClassifier = behavioralClassifier;
    }

    /**
     * Build a fully classified persona from a raw entity_connections row.
     */
    public ClassifiedPersona build(EntityConnection conn) {

        // ── Classify each dimension ──
        NameClassifier.Result name = nameClassifier.classify(conn);
        IdentityClassifier.Result id = identityClassifier.classify(conn);
        IndustryClassifier.Result naics = industryClassifier.classify(conn);
        LocationClassifier.Result loc = locationClassifier.classify(conn);
        CommodityClassifier.Result comm = commodityClassifier.classify(conn);
        BehavioralClassifier.Result behav = behavioralClassifier.classify(conn);

        // ── Assemble dimensions ──
        IdentityDimension identity = new IdentityDimension(
            name.normalizedName(),
            name.nameFirstToken(),
            name.nameTokens(),
            name.legalSuffix(),
            id.einClean(),
            id.phoneDigits(),
            id.email(),
            id.emailDomain()
        );

        IndustryDimension industry = new IndustryDimension(
            naics.naicsCode(),
            naics.naicsSector(),
            naics.naicsSubsector(),
            conn.category(),
            comm.topKeywords()
        );

        LocationDimension location = new LocationDimension(
            loc.state(),
            loc.cityNorm(),
            loc.zip3(),
            loc.zip5()
        );

        CommodityDimension commodity = new CommodityDimension(
            comm.topKeywords(),
            comm.serviceCategories()
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

        int identityScore = 0;
        if (!id.normalizedName().isBlank()) identityScore++;
        if (id.einClean() != null) identityScore++;
        if (id.phoneDigits() != null) identityScore++;
        if (id.email() != null) identityScore++;
        if (id.legalSuffix() != null) identityScore++;

        int industryScore = 0;
        if (ind.naicsCode() != null) industryScore += 2;
        industryScore += Math.min(ind.commodityKeywords().size(), 3);

        int locationScore = 0;
        if (loc.state() != null) locationScore++;
        if (loc.cityNorm() != null) locationScore++;
        if (loc.zip5() != null) locationScore += 2;
        else if (loc.zip3() != null) locationScore++;

        int commodityScore = 0;
        commodityScore += Math.min(comm.topKeywords().size(), 4);
        if (!comm.serviceCategories().isEmpty()) commodityScore++;

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
