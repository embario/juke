import Foundation
import Testing
@testable import JukeApp

/// What a failed Next tells the listener: out of songs, try again, or offline.
@Suite struct NextFeedbackTests {
    private func issue(_ error: Error) -> RadioIssue { RadioIssue.from(error, stationName: "Night Drive") }

    @Test func anEmptyStationIsExhausted() {
        let result = issue(JukeAPIError.rejected(status: 409, code: "radio_no_tracks", detail: "This station has nothing new to play right now."))
        #expect(result == .noTracks(stationName: "Night Drive"))
        #expect(result.nextOutcome == .exhausted)
        #expect(result.message.contains("run out of new songs"))
    }

    @Test func aSearchThatDidNotFinishIsTemporaryAndSaysTheStationIsNotEmpty() {
        let result = issue(JukeAPIError.server(status: 503, code: "radio_picks_unavailable", detail: "later"))
        #expect(result == .picksUnavailable(stationName: "Night Drive"))
        #expect(result.nextOutcome == .retry)
        #expect(result.message.contains("isn’t empty"))
        #expect(result.message != RadioIssue.noTracks(stationName: "Night Drive").message)
    }

    @Test func serverSpotifyAndTransportFailuresAreTemporary() {
        #expect(issue(JukeAPIError.server(status: 500, code: nil, detail: nil)).nextOutcome == .retry)
        #expect(issue(JukeAPIError.server(status: 502, code: "playback_provider_failure", detail: nil)) == .spotifyFailed)
        #expect(RadioIssue.spotifyFailed.nextOutcome == .retry)
        #expect(issue(JukeAPIError.transport("timed out")).nextOutcome == .retry)
        #expect(issue(PlaybackClientError.unavailable(502)).nextOutcome == .retry)
    }

    @Test func noConnectionIsOffline() {
        #expect(issue(JukeAPIError.offline) == .offline)
        #expect(RadioIssue.offline.nextOutcome == .offline)
        #expect(JukeAPIError.offlineCodes.contains(.notConnectedToInternet))
        #expect(!JukeAPIError.offlineCodes.contains(.timedOut), "a server that does not answer is not the phone being offline")
    }

    @Test func problemsWithTheirOwnRemedyAreNotNextOutcomes() {
        #expect(RadioIssue.spotifyNotLinked.nextOutcome == nil)
        #expect(RadioIssue.noActiveDevice.nextOutcome == nil)
        #expect(RadioIssue.signedOut.nextOutcome == nil)
    }

    @Test func theThreeOutcomesReadDifferentlyInBothPlaces() {
        let issues: [RadioIssue] = [.noTracks(stationName: "A"), .picksUnavailable(stationName: "A"), .offline]
        #expect(Set(issues.map(\.message)).count == 3)
        #expect(Set(issues.map(\.shortLabel)).count == 3)
    }

    @Test func fixtureFailuresMapToTheThreeOutcomes() {
        #expect(RadioFixtureBackend.pickError(named: "exhausted").map(issue)?.nextOutcome == .exhausted)
        #expect(RadioFixtureBackend.pickError(named: "temporary").map(issue)?.nextOutcome == .retry)
        #expect(RadioFixtureBackend.pickError(named: "offline").map(issue)?.nextOutcome == .offline)
        #expect(RadioFixtureBackend.pickError(named: "other") == nil)
    }

    // MARK: The banner

    @Test func aFailedPressShowsADismissedIssueAgain() {
        var presentation = RadioIssuePresentation()
        let empty = RadioIssue.noTracks(stationName: "Night Drive")
        let shown1 = presentation.observePress(1, issue: empty); #expect(shown1)
        presentation.dismiss(empty)
        #expect(presentation.visibleIssue(for: empty) == nil)
        // Polls do not bring it back.
        for _ in 0..<5 { presentation.observe(empty); let shown2 = presentation.observePress(1, issue: empty); #expect(!shown2) }
        #expect(presentation.visibleIssue(for: empty) == nil)
        // Pressing Next again does, every time.
        let shown3 = presentation.observePress(2, issue: empty); #expect(shown3)
        #expect(presentation.visibleIssue(for: empty) == empty)
        presentation.dismiss(empty)
        let shown4 = presentation.observePress(3, issue: empty); #expect(shown4)
        #expect(presentation.visibleIssue(for: empty) == empty)
    }

    @Test func repeatedFailuresAreCountedOnOneBannerAndStartOverWhenTheAnswerChanges() {
        var presentation = RadioIssuePresentation()
        let empty = RadioIssue.noTracks(stationName: "Night Drive")
        presentation.observe(empty); presentation.observePress(1, issue: empty)
        #expect(presentation.triesCaption == nil, "one failure reads as a plain message")
        presentation.observePress(2, issue: empty)
        presentation.observePress(3, issue: empty)
        #expect(presentation.triesCaption == "Tried 3 times")
        for _ in 0..<5 { presentation.observe(empty) }
        #expect(presentation.triesCaption == "Tried 3 times", "polls neither add to nor reset the count")

        presentation.observe(.offline); presentation.observePress(4, issue: .offline)
        #expect(presentation.tries == 1 && presentation.triesCaption == nil)
        presentation.observe(nil)
        #expect(presentation.tries == 0)
    }

    @Test func aPressCountWithoutAnIssueShowsNothing() {
        var presentation = RadioIssuePresentation()
        let shown5 = presentation.observePress(1, issue: nil); #expect(!shown5)
        #expect(presentation.tries == 0)
    }
}
