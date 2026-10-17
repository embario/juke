import Testing
@testable import JukeApp

@Suite struct VibeBackgroundGlowTests {
    @Test func glowGrowsWithIntensityAndStaysSoft() {
        let quiet = VibeBackgroundGlow.opacity(dark: false, intensity: 0.18)
        let loud = VibeBackgroundGlow.opacity(dark: false, intensity: 0.66)
        #expect(loud.primary > quiet.primary)
        #expect(loud.primary <= 0.30)
        #expect(loud.secondary < loud.primary)
    }

    @Test func darkModeUsesAStrongerGlow() {
        #expect(VibeBackgroundGlow.opacity(dark: true, intensity: 0.66).primary > VibeBackgroundGlow.opacity(dark: false, intensity: 0.66).primary)
    }

    @Test func intensityIsClamped() {
        #expect(VibeBackgroundGlow.opacity(dark: false, intensity: 5).primary == VibeBackgroundGlow.opacity(dark: false, intensity: 1).primary)
        #expect(VibeBackgroundGlow.opacity(dark: false, intensity: -3).primary == VibeBackgroundGlow.opacity(dark: false, intensity: 0).primary)
    }
}
