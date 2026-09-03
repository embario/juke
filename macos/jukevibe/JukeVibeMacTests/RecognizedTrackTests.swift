import XCTest
import Security
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

final class VibeNetworkContractTests: XCTestCase {
    func testCatalogUsesLegacyTokenAuthenticationScheme() throws {
        let url = try XCTUnwrap(URL(string: "https://neptune.tail647b75.ts.net/api/v1/tracks/"))

        let request = CatalogClient.authorizedRequest(url: url, token: "secret-token")

        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token secret-token")
    }

    func testEncryptedEnvelopeUsesServerReferenceDateContract() throws {
        let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-09-02T20:15:00Z"))
        let envelope = NeptuneVibeClient.EncryptedEnvelope(
            recordID: UUID(uuidString: "FA7512B0-43A3-424B-AE57-9A70B0FDE503")!,
            accountID: "42",
            kind: "chatMessage",
            ciphertext: Data([0x4A, 0x56]),
            modifiedAt: date,
            encryptionVersion: 1
        )

        let data = try NeptuneVibeClient.envelopeEncoder().encode(envelope)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(
            try XCTUnwrap(object["modifiedAt"] as? Double),
            date.timeIntervalSinceReferenceDate,
            accuracy: 0.001
        )
        XCTAssertNoThrow(try NeptuneVibeClient.envelopeDecoder().decode(NeptuneVibeClient.EncryptedEnvelope.self, from: data))
    }

    func testPlaybackUsesThePlatformTokenAuthenticationScheme() throws {
        let url = try XCTUnwrap(URL(string: "https://neptune.tail647b75.ts.net/api/v1/playback/state/"))

        let request = PlaybackClient.authorizedRequest(url: url, token: "secret-token")

        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token secret-token")
    }

    func testPlaybackStateDecodesSpotifyMetadataAndProgress() throws {
        let data = Data(
            """
            {
              "provider":"spotify",
              "is_playing":true,
              "progress_ms":42000,
              "track":{
                "id":"track-1",
                "uri":"spotify:track:track-1",
                "name":"Blue in Green",
                "duration_ms":327000,
                "artwork_url":"https://i.scdn.co/image/example",
                "album":{"id":"album-1","uri":"spotify:album:album-1","name":"Kind of Blue"},
                "artists":[{"id":"artist-1","uri":"spotify:artist:artist-1","name":"Miles Davis"}]
              },
              "device":{"id":"device-1","name":"This Mac","type":"Computer"}
            }
            """.utf8
        )

        let state = try JSONDecoder().decode(JukePlaybackState.self, from: data)

        XCTAssertTrue(state.isPlaying)
        XCTAssertEqual(state.progressMs, 42_000)
        XCTAssertEqual(state.track?.album?.name, "Kind of Blue")
        XCTAssertEqual(state.track?.artists?.first?.name, "Miles Davis")
        XCTAssertEqual(state.device?.name, "This Mac")
    }

    func testCatalogResultDecodesDirectArtworkURL() throws {
        let data = Data(
            """
            {
              "pk":1959,
              "name":"Blue in Green",
              "spotify_id":"0aWMVrwxPNYkKmFthzmpRi",
              "album_name":"Kind of Blue",
              "artist_names":"Miles Davis",
              "duration_ms":327000,
              "album_link":null,
              "artwork_url":"https://i.scdn.co/image/example",
              "spotify_data":{"uri":"spotify:track:0aWMVrwxPNYkKmFthzmpRi"}
            }
            """.utf8
        )

        let result = try JSONDecoder().decode(CatalogSearchResult.self, from: data)

        XCTAssertEqual(result.resolvedArtworkURL?.absoluteString, "https://i.scdn.co/image/example")
        XCTAssertEqual(result.recognizedTrack.artworkURL, result.resolvedArtworkURL)
    }

    func testCatalogBuildsSpotifyOEmbedArtworkFallback() throws {
        let data = Data(
            """
            {
              "pk":1959,
              "name":"Blue in Green",
              "spotify_id":"0aWMVrwxPNYkKmFthzmpRi",
              "spotify_data":{"uri":"spotify:track:0aWMVrwxPNYkKmFthzmpRi"}
            }
            """.utf8
        )
        let result = try JSONDecoder().decode(CatalogSearchResult.self, from: data)
        let url = try XCTUnwrap(CatalogClient.spotifyOEmbedURL(for: result))
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))

        XCTAssertEqual(url.host, "open.spotify.com")
        XCTAssertEqual(components.queryItems?.first?.value, "spotify:track:0aWMVrwxPNYkKmFthzmpRi")
    }
}

@MainActor
final class PlayerMetadataMonitorTests: XCTestCase {
    func testPlaybackPositionDoesNotChangePublishedContentIdentity() {
        let track = RecognizedTrack(
            title: "Blue in Green",
            artist: "Miles Davis",
            album: "Kind of Blue",
            isrc: nil,
            artworkURL: nil,
            appleMusicURL: nil,
            shazamID: nil,
            providerNamespace: "spotify",
            providerTrackID: "spotify-track-id"
        )
        let first = PlayerMetadataSnapshot(
            provider: .spotify,
            track: track,
            stableProviderID: "spotify-track-id",
            isPlaying: true,
            playbackPosition: 4
        )
        let later = PlayerMetadataSnapshot(
            provider: .spotify,
            track: track,
            stableProviderID: "spotify-track-id",
            isPlaying: true,
            playbackPosition: 48
        )

        XCTAssertEqual(first.contentIdentity, later.contentIdentity)
    }

    func testPollingBacksOffWhenApplicationIsInactive() {
        XCTAssertEqual(
            PlayerMetadataMonitor.pollInterval(applicationIsActive: true, hasActivePlayback: true),
            .seconds(20)
        )
        XCTAssertEqual(
            PlayerMetadataMonitor.pollInterval(applicationIsActive: false, hasActivePlayback: true),
            .seconds(60)
        )
        XCTAssertEqual(
            PlayerMetadataMonitor.pollInterval(applicationIsActive: false, hasActivePlayback: false),
            .seconds(120)
        )
    }

    func testAppleScriptProcessRunnerPreservesEmptyFields() throws {
        let fields = AppleScriptProcessRunner().executeList(
            source: "return \"first\" & ASCII character 31 & \"\" & ASCII character 31 & \"third\""
        )

        XCTAssertEqual(try XCTUnwrap(fields), ["first", "", "third"])
    }
}

final class VibeKeychainConfigurationTests: XCTestCase {
    func testQueriesUseEntitlementScopedDataProtectionKeychain() {
        let query = VibeKeychain.genericPasswordQuery(service: "test-service", account: "test-account")

        XCTAssertEqual(query[kSecUseDataProtectionKeychain as String] as? Bool, true)
        XCTAssertEqual(query[kSecAttrAccessGroup as String] as? String, "2WMS6785YD.com.juke.vibe.shared")
    }

    func testDataProtectionKeychainRoundTripDoesNotNeedLegacyACL() throws {
        let service = "com.juke.vibe.tests.\(UUID().uuidString)"
        let query = VibeKeychain.genericPasswordQuery(service: service, account: "round-trip")
        defer { SecItemDelete(query as CFDictionary) }

        var add = query
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        add[kSecValueData as String] = Data("test-value".utf8)
        XCTAssertEqual(SecItemAdd(add as CFDictionary, nil), errSecSuccess)

        var read = query
        read[kSecReturnData as String] = true
        var result: CFTypeRef?
        XCTAssertEqual(SecItemCopyMatching(read as CFDictionary, &result), errSecSuccess)
        XCTAssertEqual(result as? Data, Data("test-value".utf8))
    }
}
