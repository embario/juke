import CoreGraphics
import Foundation
import Testing
@testable import JukeApp

@Suite struct RadioLayoutTests {
    @Test func tallScreensKeepTheFullSleeve() {
        #expect(RadioLayout.sleeveSide(visibleHeight: 900) == RadioLayout.maxSleeve)
    }

    @Test func shortScreensShrinkTheSleeveToFit() {
        let expected: CGFloat = 600 - RadioLayout.fixedContentHeight
        let fitted = RadioLayout.sleeveSide(visibleHeight: 600)
        let shorter = RadioLayout.sleeveSide(visibleHeight: 560)
        #expect(fitted == expected)
        #expect(shorter < fitted)
    }

    @Test func neverShrinksPastTheMinimum() {
        #expect(RadioLayout.sleeveSide(visibleHeight: 300) == RadioLayout.minSleeve)
        #expect(RadioLayout.sleeveSide(visibleHeight: .nan) == RadioLayout.maxSleeve)
    }

    @Test func recordOffsetScalesWithTheSleeve() {
        #expect(RadioLayout.discOffset(side: 196) == 130)
        #expect(RadioLayout.discOffset(side: 120) < RadioLayout.discOffset(side: 196))
    }
}

@Suite struct RadioIssuePresentationTests {
    @Test func dismissingAnIssueSuppressesIdenticalRefreshes() {
        var presentation = RadioIssuePresentation()
        let issue = RadioIssue.unavailable("Juke could not be reached.")

        #expect(presentation.visibleIssue(for: issue) == issue)
        presentation.dismiss(issue)
        for _ in 0..<5 {
            presentation.observe(issue)
            #expect(presentation.visibleIssue(for: issue) == nil)
        }
    }

    @Test func aChangedIssueReplacesTheDismissedIssue() {
        var presentation = RadioIssuePresentation()
        let first = RadioIssue.unavailable("Juke could not be reached.")
        let next = RadioIssue.spotifyNotLinked
        presentation.dismiss(first)

        #expect(presentation.visibleIssue(for: next) == next)
        presentation.observe(next)
        #expect(presentation.dismissedIssue == nil)
        #expect(presentation.visibleIssue(for: first) == first)
    }

    @Test func clearingAnIssueAllowsItToBePresentedAgainLater() {
        var presentation = RadioIssuePresentation()
        let issue = RadioIssue.unavailable("Juke could not be reached.")
        presentation.dismiss(issue)
        presentation.observe(nil)

        #expect(presentation.dismissedIssue == nil)
        #expect(presentation.visibleIssue(for: issue) == issue)
    }
}

@Suite struct ReactionEmojiSliderTests {
    @Test func selectingMovesEmojiToTheLeftmostSlotAndPreservesTheRest() {
        var recency = ReactionEmojiRecency(["🔥", "🌙", "☀️"])

        recency.select("☀️")
        #expect(recency.values == ["☀️", "🔥", "🌙"])
        recency.select("🌙")
        #expect(recency.values == ["🌙", "☀️", "🔥"])
    }

    @Test func scrubbingMapsTouchPositionToAClampedEmojiSlot() {
        #expect(ReactionEmojiSliderLogic.slot(at: 0, width: 300, count: 3) == 0)
        #expect(ReactionEmojiSliderLogic.slot(at: 150, width: 300, count: 3) == 1)
        #expect(ReactionEmojiSliderLogic.slot(at: 300, width: 300, count: 3) == 2)
        #expect(ReactionEmojiSliderLogic.slot(at: -20, width: 300, count: 3) == 0)
        #expect(ReactionEmojiSliderLogic.slot(at: 20, width: 0, count: 3) == 0)
    }

    @Test func voiceOverAdjustableActionsChooseTheNextEmojiWithoutWrapping() {
        let choices = ["🔥", "🌙", "☀️"]
        #expect(ReactionEmojiSliderLogic.adjacent(to: "🌙", direction: 1, in: choices) == "☀️")
        #expect(ReactionEmojiSliderLogic.adjacent(to: "🌙", direction: -1, in: choices) == "🔥")
        #expect(ReactionEmojiSliderLogic.adjacent(to: nil, direction: 1, in: choices) == "🔥")
        #expect(ReactionEmojiSliderLogic.adjacent(to: "☀️", direction: 1, in: choices) == nil)
    }

    @Test func recentEmojiOrderPersistsSeparatelyForEachAccount() {
        let suite = "ReactionEmojiSliderTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let one = RadioPreferences(defaults: defaults, accountID: "one")
        let two = RadioPreferences(defaults: defaults, accountID: "two")

        one.recentEmojiReactions = ["🌙", "🔥"]
        #expect(RadioPreferences(defaults: defaults, accountID: "one").recentEmojiReactions == ["🌙", "🔥"])
        #expect(two.recentEmojiReactions.isEmpty)
    }
}
