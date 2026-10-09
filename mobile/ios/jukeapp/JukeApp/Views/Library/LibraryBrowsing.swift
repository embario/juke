import SwiftUI

/// Pure helpers for Library browsing (artist -> albums, album -> tracks).
enum LibraryBrowsing {
    /// The catalog row for a crate item. Matched on the exact Spotify id only: a same-name entry with another id is a different artist/album.
    static func match(_ results: [CatalogSearchResult], spotifyID: String) -> CatalogSearchResult? {
        results.first { $0.spotifyID == spotifyID }
    }

    static func trackSeed(_ track: CatalogTrackDetail, in album: CatalogAlbumDetail, artist: String?) -> Radio.Seed? {
        guard let id = track.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .track, spotifyId: id, title: track.name, subtitle: artist ?? album.name, artworkUrl: album.spotifyData?.images?.first)
    }

    static func albumSeed(_ album: CatalogAlbumSummary, artist: String?) -> Radio.Seed? {
        guard let id = album.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .album, spotifyId: id, title: album.name, subtitle: artist, artworkUrl: album.spotifyData?.images?.first)
    }

    static func albumSeed(_ album: CatalogAlbumDetail, artist: String?) -> Radio.Seed? {
        guard let id = album.spotifyID, !id.isEmpty else { return nil }
        return Radio.Seed(kind: .album, spotifyId: id, title: album.name, subtitle: artist, artworkUrl: album.spotifyData?.images?.first)
    }

    static func duration(_ ms: Int?) -> String? {
        ms.map { MemorySong.timestamp(Double($0) / 1000) }
    }

    /// "5 tracks · 1959": what the album pane says under the title.
    static func albumFacts(_ album: CatalogAlbumDetail) -> String {
        var parts: [String] = []
        let count = album.tracks.isEmpty ? album.totalTracks : album.tracks.count
        if let count, count > 0 { parts.append("\(count) \(count == 1 ? "track" : "tracks")") }
        if let year = album.releaseDate?.prefix(4), year.count == 4 { parts.append(String(year)) }
        return parts.joined(separator: " · ")
    }

    /// A disc of an album's tracklist.
    struct Disc: Identifiable, Equatable {
        let number: Int
        let tracks: [Int]  // indices into the album's tracks
        var id: Int { number }
    }

    /// The tracklist by disc, in play order. A one-disc album has one disc; tracks without a number keep their order, last.
    static func discs(_ tracks: [CatalogTrackDetail]) -> [Disc] {
        let order = tracks.indices.sorted { lhs, rhs in
            let a = tracks[lhs], b = tracks[rhs]
            if (a.discNumber ?? 1) != (b.discNumber ?? 1) { return (a.discNumber ?? 1) < (b.discNumber ?? 1) }
            if (a.trackNumber ?? Int.max) != (b.trackNumber ?? Int.max) { return (a.trackNumber ?? Int.max) < (b.trackNumber ?? Int.max) }
            return lhs < rhs
        }
        var result: [Disc] = []
        for index in order {
            let number = tracks[index].discNumber ?? 1
            if let last = result.last, last.number == number { result[result.count - 1] = Disc(number: number, tracks: last.tracks + [index]) }
            else { result.append(Disc(number: number, tracks: [index])) }
        }
        return result
    }

    /// "jazz · modal jazz": the artist pane's line under the name.
    static func genreLine(_ artist: CatalogArtistDetail?, limit: Int = 3) -> String? {
        let names = (artist?.genres.map(\.name) ?? []).filter { !$0.isEmpty }.prefix(limit)
        return names.isEmpty ? nil : names.joined(separator: " · ")
    }
}

/// Where an artist or album screen can be opened from outside Library (Radio's now-playing card, a memory's song).
enum DetailRoute: Identifiable, Hashable {
    case artist(title: String, spotifyID: String)
    case album(title: String, spotifyID: String, artist: String?)

    var id: String {
        switch self {
        case .artist(_, let id): "artist:\(id)"
        case .album(_, let id, _): "album:\(id)"
        }
    }

    var title: String {
        switch self {
        case .artist(let title, _), .album(let title, _, _): title
        }
    }

    /// The route for a radio song's artist; nil when the song carries no artist id.
    static func artist(of track: Radio.Track) -> DetailRoute? {
        guard let id = track.artistId, !id.isEmpty else { return nil }
        return .artist(title: track.artist, spotifyID: id)
    }

    /// The route for a radio song's album; nil when the song carries no album id or name.
    static func album(of track: Radio.Track) -> DetailRoute? {
        guard let id = track.albumId, !id.isEmpty, let name = track.album, !name.isEmpty else { return nil }
        return .album(title: name, spotifyID: id, artist: track.artist)
    }
}

private struct DetailSheetCloseKey: EnvironmentKey { static let defaultValue: (@MainActor () -> Void)? = nil }

extension EnvironmentValues {
    /// Set when an artist or album screen is shown in a sheet, so starting a station from it can close the sheet.
    var detailSheetClose: (@MainActor () -> Void)? {
        get { self[DetailSheetCloseKey.self] }
        set { self[DetailSheetCloseKey.self] = newValue }
    }
}

extension View {
    /// Presents the artist or album screen for `route` in a sheet with its own navigation.
    func detailSheet(_ route: Binding<DetailRoute?>) -> some View {
        sheet(item: route) { current in
            NavigationStack {
                Group {
                    switch current {
                    case .artist(let title, let id): ArtistDetailView(title: title, spotifyID: id)
                    case .album(let title, let id, let artist): AlbumDetailView(title: title, spotifyID: id, artist: artist)
                    }
                }
                .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { route.wrappedValue = nil }.accessibilityIdentifier("detail.done") } }
            }
            .environment(\.detailSheetClose) { route.wrappedValue = nil }
        }
    }
}

/// Shared actions: play something now, or start a station from a seed.
@MainActor
struct LibraryActions {
    let model: VibeAppModel

    func play(spotifyID: String, kind: String) async -> String? {
        guard let token = model.session?.accessToken else { return "Sign in to play." }
        do { _ = try await PlaybackClient().play(token: token, spotifyID: spotifyID, kind: kind, deviceID: nil); return nil }
        catch { return (error as? LocalizedError)?.errorDescription ?? "Spotify couldn’t play that." }
    }

    func station(from seed: Radio.Seed) {
        model.coordinator.openNewStation(.init(start: .records, seeds: [seed], feelings: []))
        model.tab = .radio
    }
}

/// Loads a catalog detail for a crate item, resolving its catalog id through search.
enum CatalogLoad<Value: Sendable>: Sendable {
    case loading, loaded(Value), failed(String)
}
