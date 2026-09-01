import XCTest
@testable import Juke_Vibe

final class RecognizedTrackTests: XCTestCase {
    func testProviderIdentityTakesPriorityOverMetadata() {
        let track = makeTrack(providerNamespace: "spotify", providerTrackID: "4uLU6hMCjMI75M1A2tKUQC")

        XCTAssertEqual(track.identityKey, "provider:spotify:4uLU6hMCjMI75M1A2tKUQC")
    }

    func testMetadataComparisonNormalizesCaseAndWhitespace() {
        let first = makeTrack(title: "  A Case of You ", artist: "Joni Mitchell")
        let second = makeTrack(title: "a case of you", artist: "JONI  MITCHELL")

        XCTAssertTrue(first.isLikelySameRecording(as: second))
    }

    private func makeTrack(
        title: String = "A Case of You",
        artist: String = "Joni Mitchell",
        providerNamespace: String? = nil,
        providerTrackID: String? = nil
    ) -> RecognizedTrack {
        RecognizedTrack(
            title: title,
            artist: artist,
            album: "Blue",
            isrc: nil,
            artworkURL: nil,
            appleMusicURL: nil,
            shazamID: nil,
            providerNamespace: providerNamespace,
            providerTrackID: providerTrackID
        )
    }
}
