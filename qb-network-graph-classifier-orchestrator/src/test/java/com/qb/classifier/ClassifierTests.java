package com.qb.classifier;

import com.qb.classifier.classifier.PersonaBuilder;
import com.qb.classifier.classifier.impl.*;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.EntityConnection;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Nested;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ClassifierTests {

    // ── NameClassifier ────────────────────────────────────────

    @Nested
    class NameClassifierTests {

        private final NameClassifier classifier = new NameClassifier();

        private NameClassifier.Result normalize(String name) {
            return classifier.classify(new EntityConnection(
                0, 0, "", name, null, null, null, null, null, null,
                null, null, null, null, null, null, null, null, null, null, null, null
            ));
        }

        @Test void normalCase() {
            var r = normalize("Bob's Plumbing LLC");
            assertEquals("BOBS PLUMBING", r.normalizedName());
            assertEquals("BOBS", r.nameFirstToken());
            assertEquals(List.of("BOBS", "PLUMBING"), r.nameTokens());
            assertEquals("LLC", r.legalSuffix());
        }

        @Test void corporationSuffix() {
            var r = normalize("Acme Construction Co Inc.");
            assertEquals("ACME CONSTRUCTION", r.normalizedName());
            assertEquals("INC", r.legalSuffix());
        }

        @Test void noSuffix() {
            var r = normalize("Capital City Plumbing");
            assertEquals("CAPITAL CITY PLUMBING", r.normalizedName());
            assertNull(r.legalSuffix());
        }

        @Test void punctuation() {
            var r = normalize("O'Brien & Sons, Inc.");
            assertEquals("OBRIEN SONS", r.normalizedName());
            assertEquals("INC", r.legalSuffix());
        }

        @Test void empty() {
            var r = normalize(null);
            assertEquals("", r.normalizedName());
            assertTrue(r.nameTokens().isEmpty());
        }

        @Test void noiseWords() {
            var r = normalize("The A & B Company LLC");
            assertEquals("LLC", r.legalSuffix());
            assertFalse(r.nameTokens().contains("THE"));
        }
    }

    // ── IndustryClassifier ───────────────────────────────────

    @Nested
    class IndustryClassifierTests {

        @Test void exactMatch() {
            var r = IndustryClassifier.classifyCategory("Plumbing Supply");
            assertTrue(r.classified());
            assertEquals("423720", r.naicsCode());
            assertEquals("42", r.naicsSector());
            assertEquals("423", r.naicsSubsector());
            assertEquals("exact", r.source());
        }

        @Test void keywordMatch() {
            var r = IndustryClassifier.classifyCategory("General dumpster services");
            assertTrue(r.classified());
            assertEquals("562111", r.naicsCode());
            assertEquals("keyword", r.source());
        }

        @Test void noMatch() {
            var r = IndustryClassifier.classifyCategory("Quantum Computing Research");
            assertFalse(r.classified());
            assertEquals("none", r.source());
        }

        @Test void nullInput() {
            var r = IndustryClassifier.classifyCategory(null);
            assertFalse(r.classified());
        }
    }

    // ── IdentityClassifier ───────────────────────────────────

    @Nested
    class IdentityClassifierTests {

        @Test void einWithDash() {
            assertEquals("743218976", IdentityClassifier.cleanEin("74-3218976"));
        }

        @Test void einTooShort() {
            assertNull(IdentityClassifier.cleanEin("74-321"));
        }

        @Test void phoneWithFormatting() {
            assertEquals("5125550101", IdentityClassifier.cleanPhone("512-555-0101"));
        }

        @Test void phoneWithCountryCode() {
            assertEquals("5125550101", IdentityClassifier.cleanPhone("+1-512-555-0101"));
        }

        @Test void emailDomain() {
            assertEquals("acmeconstruction.com",
                IdentityClassifier.emailDomain("marcus@acmeconstruction.com"));
        }

        @Test void nullEmail() {
            assertNull(IdentityClassifier.emailDomain(null));
        }
    }

    // ── LocationClassifier ───────────────────────────────────

    @Nested
    class LocationClassifierTests {

        @Test void normalCase() {
            var r = LocationClassifier.normalize("Austin", "TX", "78745");
            assertEquals("TX", r.state());
            assertEquals("AUSTIN", r.cityNorm());
            assertEquals("787", r.zip3());
            assertEquals("78745", r.zip5());
        }

        @Test void zipWithExtension() {
            var r = LocationClassifier.normalize(null, null, "78745-1234");
            assertEquals("78745", r.zip5());
            assertEquals("787", r.zip3());
        }

        @Test void allNull() {
            var r = LocationClassifier.normalize(null, null, null);
            assertNull(r.state());
            assertNull(r.cityNorm());
        }
    }

    // ── BehavioralClassifier ─────────────────────────────────

    @Nested
    class BehavioralClassifierTests {

        @Test void mediumBracket() {
            var r = BehavioralClassifier.classifyBehavior(new BigDecimal("84000.00"), 47L);
            assertEquals("MEDIUM", r.volumeBracket());
            assertEquals(47, r.transactionCount());
            assertNotNull(r.avgTransaction());
        }

        @Test void veryHighBracket() {
            var r = BehavioralClassifier.classifyBehavior(new BigDecimal("2500000.00"), 150L);
            assertEquals("VERY_HIGH", r.volumeBracket());
        }

        @Test void nullVolume() {
            var r = BehavioralClassifier.classifyBehavior(null, null);
            assertNull(r.volumeBracket());
        }
    }

    // ── CommodityClassifier ──────────────────────────────────

    @Nested
    class CommodityClassifierTests {

        @Test void explicitCommodity() {
            var r = CommodityClassifier.extract("PVC pipe, copper fittings", null, null);
            assertFalse(r.topKeywords().isEmpty());
        }

        @Test void fromCategory() {
            var r = CommodityClassifier.extract(null, "Plumbing Supply", null);
            assertTrue(r.topKeywords().contains("plumbing"));
        }

        @Test void fromDisplayName() {
            var r = CommodityClassifier.extract(null, null, "Bob's Roofing Inc");
            assertTrue(r.topKeywords().contains("roofing"));
        }

        @Test void allNull() {
            var r = CommodityClassifier.extract(null, null, null);
            assertTrue(r.topKeywords().isEmpty());
        }
    }

    // ── PersonaBuilder (integration) ─────────────────────────

    @Nested
    class PersonaBuilderTests {

        private final PersonaBuilder builder = new PersonaBuilder(
            new NameClassifier(),
            new IdentityClassifier(),
            new IndustryClassifier(),
            new LocationClassifier(),
            new CommodityClassifier(),
            new BehavioralClassifier()
        );

        @Test void fullRow() {
            EntityConnection conn = new EntityConnection(
                1L, 42L, "vendor",
                "Bob's Plumbing LLC", "74-3218976", "Bob Smith",
                "bob@bobsplumbing.com", "512-555-0101",
                "Plumbing Supply", "PVC pipe, copper fittings",
                "123 Main St", "Austin", "TX", "78745",
                "www.bobsplumbing.com", new BigDecimal("50000"),
                "Net 30",
                new BigDecimal("84000.00"), 47L,
                LocalDate.of(2023, 3, 15), LocalDate.of(2025, 1, 10),
                null
            );

            ClassifiedPersona p = builder.build(conn);

            // Identity
            assertEquals("BOBS PLUMBING", p.identity().normalizedName());
            assertEquals("BOBS", p.identity().nameFirstToken());
            assertEquals("LLC", p.identity().legalSuffix());
            assertEquals("743218976", p.identity().einClean());
            assertEquals("5125550101", p.identity().phoneDigits());
            assertEquals("bobsplumbing.com", p.identity().emailDomain());

            // Industry
            assertEquals("423720", p.industry().naicsCode());
            assertEquals("42", p.industry().naicsSector());
            assertFalse(p.industry().commodityKeywords().isEmpty());

            // Location
            assertEquals("TX", p.location().state());
            assertEquals("AUSTIN", p.location().cityNorm());
            assertEquals("787", p.location().zip3());
            assertEquals("78745", p.location().zip5());

            // Behavioral
            assertEquals("MEDIUM", p.behavioral().volumeBracket());
            assertEquals(47, p.behavioral().transactionCount());
            assertEquals("Net 30", p.behavioral().paymentTerms());

            // Sparsity — should be high with all fields populated
            assertTrue(p.sparsity().identity() >= 4);
            assertTrue(p.sparsity().location() >= 3);
        }

        @Test void sparseRow() {
            EntityConnection conn = new EntityConnection(
                3L, 99L, "vendor",
                "BP Supply", null, null,
                null, null,
                null, null,
                null, null, "TX", null,
                null, null, null,
                null, null, null, null, null
            );

            ClassifiedPersona p = builder.build(conn);

            assertEquals("BP SUPPLY", p.identity().normalizedName());
            assertNull(p.identity().einClean());
            assertNull(p.industry().naicsCode());
            assertEquals("TX", p.location().state());
            assertNull(p.behavioral().volumeBracket());

            // Sparsity should be low
            assertTrue(p.sparsity().identity() <= 2);
            assertEquals(0, p.sparsity().behavioral());
        }
    }
}
