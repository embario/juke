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

    func testSpotifyConnectionUsesJukeAuthenticatedConnectFlow() throws {
        let request = try JukeAuthenticationService.spotifyConnectTicketRequest(token: "secret token")
        let url = try XCTUnwrap(request.url)
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))

        XCTAssertEqual(components.path, "/api/v1/auth/spotify/connect-ticket/")
        XCTAssertNil(components.query)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token secret token")
        let body = try XCTUnwrap(request.httpBody)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: String])
        XCTAssertEqual(
            payload["return_to"],
            "https://neptune.tail647b75.ts.net/"
        )
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

    func testAlbumDetailDecodesTracksAndRelatedAlbums() throws {
        let data = Data(
            """
            {
              "pk":1959,
              "name":"Kind of Blue",
              "description":"A landmark recording.",
              "total_tracks":2,
              "tracks":[
                {"pk":1,"name":"So What","spotify_id":"track-1","duration_ms":560000,"track_number":1,"disc_number":1}
              ],
              "related_albums":[{"pk":2,"name":"Sketches of Spain","total_tracks":5}]
            }
            """.utf8
        )

        let album = try JSONDecoder().decode(CatalogAlbumDetail.self, from: data)

        XCTAssertEqual(album.tracks.first?.name, "So What")
        XCTAssertEqual(album.tracks.first?.durationMs, 560_000)
        XCTAssertEqual(album.relatedAlbums.first?.name, "Sketches of Spain")
    }
}

@MainActor
final class PlayerMetadataMonitorTests: XCTestCase {
    func testChatTextSizeRangeProtectsCompactAndReadableLayouts() {
        XCTAssertEqual(AppModel.chatTextSizeRange, 14.0...22.0)
        XCTAssertTrue(AppModel.chatTextSizeRange.contains(AppModel.defaultChatTextSize))
    }

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

@MainActor
final class PlayerMetadataLifecycleTests: XCTestCase {
    func testMissingLocalPlaybackClearsNowPlaying() {
        let monitor = PlayerMetadataMonitor(readCurrentPlayback: { nil })
        let controller = MusicDetectionController(monitor: monitor)
        monitor.onSnapshot?(snapshot())
        XCTAssertTrue(controller.isPlaying)
        monitor.onSnapshot?(nil)
        XCTAssertNil(controller.track)
        XCTAssertNil(controller.providerName)
        XCTAssertFalse(controller.isPlaying)
        XCTAssertFalse(controller.isAudioPresent)
        XCTAssertEqual(controller.playbackPosition, 0)
        XCTAssertEqual(controller.playbackDuration, 0)
        XCTAssertNil(controller.playbackDeviceName)
        XCTAssertFalse(controller.canControlPlayback)
    }

    func testMissingLocalPlaybackPreservesRemoteSpotifyDevice() throws {
        let monitor = PlayerMetadataMonitor(readCurrentPlayback: { nil })
        let controller = MusicDetectionController(monitor: monitor)
        monitor.onSnapshot?(snapshot())
        let state = try JSONDecoder().decode(JukePlaybackState.self, from: Data("""
            {"provider":"spotify","is_playing":true,"progress_ms":42000,
             "track":{"id":"remote-track","name":"Remote song","duration_ms":180000},
             "device":{"id":"remote-device","name":"Living Room"}}
            """.utf8))
        controller.apply(state)
        monitor.onSnapshot?(nil)
        XCTAssertEqual(controller.track?.title, "Remote song")
        XCTAssertTrue(controller.isPlaying)
        XCTAssertEqual(controller.playbackPosition, 42)
        XCTAssertEqual(controller.playbackDeviceName, "Living Room")
    }

    func testUnlinkedSpotifyDoesNotDisableAppleMusicControls() {
        let monitor = PlayerMetadataMonitor(readCurrentPlayback: { nil })
        let controller = MusicDetectionController(monitor: monitor)
        controller.spotifyPlaybackAccess = .spectator
        controller.prefersSpotifySpectatorMode = false
        monitor.onSnapshot?(snapshot())
        XCTAssertTrue(controller.canControlPlayback)
        controller.providerName = PlayerMetadataSnapshot.Provider.spotify.rawValue
        XCTAssertFalse(controller.canControlPlayback)
    }

    func testSameTrackSeekRebasesPlaybackPosition() async throws {
        let reader = SuspendedMetadataReader()
        let monitor = PlayerMetadataMonitor(readCurrentPlayback: { await reader.read() })
        let controller = MusicDetectionController(monitor: monitor)
        monitor.refreshNow()
        try await reader.waitForReads(1)
        await reader.finish(0, with: snapshot(position: 10))
        await monitor.refreshTask?.value
        XCTAssertEqual(controller.playbackPosition, 10)
        monitor.refreshNow()
        try await reader.waitForReads(2)
        await reader.finish(1, with: snapshot(position: 90))
        await monitor.refreshTask?.value
        XCTAssertEqual(controller.playbackPosition, 90)
        monitor.stop()
    }

    func testCancelledRefreshCannotPublishOrClearRestartedRefresh() async throws {
        let reader = SuspendedMetadataReader()
        let monitor = PlayerMetadataMonitor(readCurrentPlayback: { await reader.read() })
        var publications: [String?] = []
        monitor.onSnapshot = { publications.append($0?.track.title) }
        monitor.refreshNow()
        try await reader.waitForReads(1)
        let cancelledRefresh = monitor.refreshTask
        monitor.stop()
        monitor.refreshNow()
        try await reader.waitForReads(2)
        await reader.finish(0, with: snapshot(title: "Cancelled"))
        await cancelledRefresh?.value
        monitor.refreshNow()
        let count = await reader.count
        XCTAssertEqual(count, 2, "Old completion must not clear the newer in-flight handle")
        XCTAssertEqual(publications.count, 1, "Only stop's nil publication is expected")
        await reader.finish(1, with: snapshot(title: "Restarted"))
        await monitor.refreshTask?.value
        XCTAssertEqual(publications.last!, "Restarted")
        monitor.refreshNow()
        try await reader.waitForReads(3)
        await reader.finish(2, with: nil)
        await monitor.refreshTask?.value
        XCTAssertNil(publications.last!)
        monitor.stop()
    }

    private func snapshot(title: String = "Local song", position: TimeInterval = 12) -> PlayerMetadataSnapshot {
        PlayerMetadataSnapshot(
            provider: .appleMusic,
            track: RecognizedTrack(title: title, artist: "Artist", album: nil, isrc: nil,
                artworkURL: nil, appleMusicURL: nil, shazamID: nil, trackDuration: 180),
            stableProviderID: "local-track", isPlaying: true, playbackPosition: position
        )
    }
}

private actor SuspendedMetadataReader {
    private var continuations: [CheckedContinuation<PlayerMetadataSnapshot?, Never>] = []
    var count: Int { continuations.count }

    func read() async -> PlayerMetadataSnapshot? {
        await withCheckedContinuation { continuations.append($0) }
    }

    func waitForReads(_ expected: Int) async throws {
        let deadline = Date().addingTimeInterval(3)
        while count < expected {
            guard Date() < deadline else {
                throw NSError(domain: "MetadataReadTimeout", code: expected)
            }
            try await Task.sleep(for: .milliseconds(1))
        }
    }

    func finish(_ index: Int, with snapshot: PlayerMetadataSnapshot?) {
        continuations[index].resume(returning: snapshot)
    }
}
