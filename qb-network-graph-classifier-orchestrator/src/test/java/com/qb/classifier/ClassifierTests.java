package com.qb.classifier;

import com.qb.classifier.classify.*;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.EntityConnection;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Nested;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ClassifierTests {

    // ── NameNormalizer ────────────────────────────────────────

    @Nested
    class NameNormalizerTests {

        @Test void normalCase() {
            var r = NameNormalizer.normalize("Bob's Plumbing LLC");
            assertEquals("BOBS PLUMBING", r.normalizedName());
            assertEquals("BOBS", r.nameFirstToken());
            assertEquals(List.of("BOBS", "PLUMBING"), r.nameTokens());
            assertEquals("LLC", r.legalSuffix());
        }

        @Test void corporationSuffix() {
            var r = NameNormalizer.normalize("Acme Construction Co Inc.");
            assertEquals("ACME CONSTRUCTION", r.normalizedName());
            assertEquals("INC", r.legalSuffix());
        }

        @Test void noSuffix() {
            var r = NameNormalizer.normalize("Capital City Plumbing");
            assertEquals("CAPITAL CITY PLUMBING", r.normalizedName());
            assertNull(r.legalSuffix());
        }

        @Test void punctuation() {
            var r = NameNormalizer.normalize("O'Brien & Sons, Inc.");
            assertEquals("OBRIEN SONS", r.normalizedName());
            assertEquals("INC", r.legalSuffix());
        }

        @Test void empty() {
            var r = NameNormalizer.normalize(null);
            assertEquals("", r.normalizedName());
            assertTrue(r.nameTokens().isEmpty());
        }

        @Test void noiseWords() {
            var r = NameNormalizer.normalize("The A & B Company LLC");
            assertEquals("LLC", r.legalSuffix());
            // "THE", "A", "&", "B" filtered (single char or noise)
            assertFalse(r.nameTokens().contains("THE"));
        }
    }

    // ── IndustryClassifier ───────────────────────────────────

    @Nested
    class IndustryClassifierTests {

        @Test void exactMatch() {
            var r = IndustryClassifier.classify("Plumbing Supply");
            assertTrue(r.classified());
            assertEquals("423720", r.naicsCode());
            assertEquals("42", r.naicsSector());
            assertEquals("423", r.naicsSubsector());
            assertEquals("exact", r.source());
        }

        @Test void keywordMatch() {
            var r = IndustryClassifier.classify("General dumpster services");
            assertTrue(r.classified());
            assertEquals("562111", r.naicsCode());
            assertEquals("keyword", r.source());
        }

        @Test void noMatch() {
            var r = IndustryClassifier.classify("Quantum Computing Research");
            assertFalse(r.classified());
            assertEquals("none", r.source());
        }

        @Test void nullInput() {
            var r = IndustryClassifier.classify(null);
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

    // ── LocationNormalizer ────────────────────────────────────

    @Nested
    class LocationNormalizerTests {

        @Test void normalCase() {
            var r = LocationNormalizer.normalize("Austin", "TX", "78745");
            assertEquals("TX", r.state());
            assertEquals("AUSTIN", r.cityNorm());
            assertEquals("787", r.zip3());
            assertEquals("78745", r.zip5());
        }

        @Test void zipWithExtension() {
            var r = LocationNormalizer.normalize(null, null, "78745-1234");
            assertEquals("78745", r.zip5());
            assertEquals("787", r.zip3());
        }

        @Test void allNull() {
            var r = LocationNormalizer.normalize(null, null, null);
            assertNull(r.state());
            assertNull(r.cityNorm());
        }
    }

    // ── BehavioralClassifier ─────────────────────────────────

    @Nested
    class BehavioralClassifierTests {

        @Test void mediumBracket() {
            var r = BehavioralClassifier.classify(new BigDecimal("84000.00"), 47L);
            assertEquals("MEDIUM", r.volumeBracket());
            assertEquals(47, r.transactionCount());
            assertNotNull(r.avgTransaction());
        }

        @Test void veryHighBracket() {
            var r = BehavioralClassifier.classify(new BigDecimal("2500000.00"), 150L);
            assertEquals("VERY_HIGH", r.volumeBracket());
        }

        @Test void nullVolume() {
            var r = BehavioralClassifier.classify(null, null);
            assertNull(r.volumeBracket());
        }
    }

    // ── CommodityExtractor ───────────────────────────────────

    @Nested
    class CommodityExtractorTests {

        @Test void explicitCommodity() {
            var r = CommodityExtractor.extract("PVC pipe, copper fittings", null, null);
            assertFalse(r.topKeywords().isEmpty());
        }

        @Test void fromCategory() {
            var r = CommodityExtractor.extract(null, "Plumbing Supply", null);
            assertTrue(r.topKeywords().contains("plumbing"));
        }

        @Test void fromDisplayName() {
            var r = CommodityExtractor.extract(null, null, "Bob's Roofing Inc");
            assertTrue(r.topKeywords().contains("roofing"));
        }

        @Test void allNull() {
            var r = CommodityExtractor.extract(null, null, null);
            assertTrue(r.topKeywords().isEmpty());
        }
    }

    // ── PersonaBuilder (integration) ─────────────────────────

    @Nested
    class PersonaBuilderTests {

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

            ClassifiedPersona p = PersonaBuilder.build(conn);

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

            ClassifiedPersona p = PersonaBuilder.build(conn);

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
