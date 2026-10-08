import Testing
@testable import JukeApp

@MainActor @Suite struct NewStationWizardTests {
    private func seed(_ id: String) -> Radio.Seed { Radio.Seed(kind: .track, spotifyId: id, title: "Song \(id)", subtitle: nil, artworkUrl: nil) }

    @Test func emptyDraftsAskHowToBegin() {
        #expect(NewStationWizard.initialPage(for: .init()) == .start)
        #expect(NewStationWizard.initialPage(for: .init(start: .records, seeds: [seed("a")], feelings: [])) == .first)
        #expect(NewStationWizard.initialPage(for: .init(start: .feelings, seeds: [], feelings: ["🔥"])) == .first)
    }

    @Test func theChosenStepNeedsAPickButTheOtherStepNeverBlocks() {
        let flow = NewStationFlow(draft: .init(start: .feelings, seeds: [], feelings: []))
        #expect(!NewStationWizard.canAdvance(from: .first, flow: flow))
        #expect(NewStationWizard.canAdvance(from: .second, flow: flow))
        #expect(NewStationWizard.advanceLabel(from: .second, flow: flow) == "Skip")
        flow.toggleFeeling("🔥")
        #expect(NewStationWizard.canAdvance(from: .first, flow: flow))
        #expect(!NewStationWizard.canAdvance(from: .first, flow: NewStationFlow(draft: .init(start: .records, seeds: [], feelings: ["🔥"]))))
    }

    @Test func theSecondPageIsTheOtherStep() {
        #expect(NewStationPage.first.step(path: .records) == .records)
        #expect(NewStationPage.second.step(path: .records) == .feelings)
        #expect(NewStationPage.second.step(path: .feelings) == .records)
        #expect(NewStationPage.start.step(path: .records) == nil)
        #expect(NewStationPage.finish.next == nil)
        #expect(NewStationPage.start.previous == nil)
    }

    @Test func finishNeedsAtLeastOnePick() {
        #expect(!NewStationWizard.canAdvance(from: .finish, flow: NewStationFlow(draft: .init())))
        #expect(NewStationWizard.canAdvance(from: .finish, flow: NewStationFlow(draft: .init(start: .records, seeds: [seed("a")], feelings: []))))
    }

    @Test func theDescriptionJoinsTheFeelingsOnce() {
        #expect(NewStationWizard.feelings(["🔥"], description: "  slow   and warm ") == ["🔥", "slow and warm"])
        #expect(NewStationWizard.feelings(["🔥", "slow and warm"], description: "slow and warm") == ["🔥", "slow and warm"])
        #expect(NewStationWizard.feelings(["🔥"], description: "   ") == ["🔥"])
        let long = String(repeating: "a", count: 90)
        #expect(NewStationWizard.feelings([], description: long).first?.count == NewStationFlow.maxPhraseLength)
        let full = (1...NewStationFlow.maxFeelings).map { "f\($0)" }
        #expect(NewStationWizard.feelings(full, description: "one more") == full)
    }

    @Test func blankNamesLetTheServerChoose() {
        #expect(NewStationWizard.name("   ") == nil)
        #expect(NewStationWizard.name("  Late  night ") == "Late night")
        #expect(NewStationWizard.name(String(repeating: "x", count: 200))?.count == 80)
    }
}
