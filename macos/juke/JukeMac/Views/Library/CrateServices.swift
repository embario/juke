import Foundation

/// Reads the Library crate (`GET radio/crate/`). `JukeAPI` is the live one.
protocol CrateSource: Sendable {
    func crate(kind: Radio.SeedKind, query: String?) async throws -> [Radio.CrateItem]
}

/// Creates stations (`POST radio/stations/`). `JukeAPI` is the live one.
protocol StationCreator: Sendable {
    func createStation(name: String?, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station
}

extension JukeAPI: CrateSource, StationCreator {}

/// What Library and New Station talk to. UI tests get an offline fixture so
/// the crate works without a backend.
struct CrateServices: Sendable {
    var crate: any CrateSource
    var stations: any StationCreator

    @MainActor
    static func make(api: JukeAPI) -> CrateServices {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            return CrateServices(crate: FixtureCrate(), stations: FixtureCrate())
        }
        #endif
        return CrateServices(crate: api, stations: api)
    }
}

/// Builds `CrateServices` once per screen (held in `@State`), so a body pass
/// never rebuilds it.
@MainActor
final class CrateServicesCache {
    private var services: CrateServices?

    func services(api: JukeAPI) -> CrateServices {
        if let services { return services }
        let made = CrateServices.make(api: api)
        services = made
        return made
    }
}

/// Creates a station and hands it to the radio: it starts after the current
/// song, so whatever is playing is never cut off.
@MainActor
struct StationStarter {
    static let maxRecords = 3

    let creator: any StationCreator
    let coordinator: JukeCoordinator

    @discardableResult
    func start(seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station {
        let station = try await creator.createStation(name: nil, seeds: Array(seeds.prefix(Self.maxRecords)), feelings: feelings)
        coordinator.requestStation(station.id, timing: .afterCurrentSong)
        return station
    }
}

#if DEBUG
/// Offline crate used by UI tests (`--uitesting`).
struct FixtureCrate: CrateSource, StationCreator {
    private static func track(_ id: String, _ title: String, _ artist: String) -> Radio.CrateItem {
        Radio.CrateItem(id: Radio.ID(id), kind: .track, spotifyId: id, title: title, subtitle: artist, artworkUrl: nil, track: nil)
    }

    private static func other(_ kind: Radio.SeedKind, _ id: String, _ title: String, _ subtitle: String) -> Radio.CrateItem {
        Radio.CrateItem(id: Radio.ID(id), kind: kind, spotifyId: id, title: title, subtitle: subtitle, artworkUrl: nil, track: nil)
    }

    static let tracks = [
        track("fx-midnight", "Midnight City", "M83"),
        track("fx-nightcall", "Nightcall", "Kavinsky"),
        track("fx-blue", "Blue in Green", "Miles Davis"),
        track("fx-maria", "Maria También", "Khruangbin"),
        track("fx-pinkmoon", "Pink Moon", "Nick Drake"),
        track("fx-sowhat", "So What", "Miles Davis"),
        track("fx-lovely", "Lovely Day", "Bill Withers"),
    ]
    static let artists = [
        other(.artist, "fx-a-miles", "Miles Davis", "Artist"),
        other(.artist, "fx-a-m83", "M83", "Artist"),
        other(.artist, "fx-a-khruangbin", "Khruangbin", "Artist"),
        other(.artist, "fx-a-drake", "Nick Drake", "Artist"),
    ]
    static let albums = [
        other(.album, "fx-b-kind", "Kind of Blue", "Miles Davis"),
        other(.album, "fx-b-hurry", "Hurry Up, We're Dreaming", "M83"),
        other(.album, "fx-b-pink", "Pink Moon", "Nick Drake"),
        other(.album, "fx-b-con", "Con Todo El Mundo", "Khruangbin"),
    ]

    func crate(kind: Radio.SeedKind, query: String?) async throws -> [Radio.CrateItem] {
        let pool = switch kind {
        case .artist: Self.artists
        case .album: Self.albums
        default: Self.tracks
        }
        guard let needle = query?.lowercased(), !needle.isEmpty else { return pool }
        return pool.filter { "\($0.title) \($0.subtitle ?? "")".lowercased().contains(needle) }
    }

    func createStation(name: String?, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station {
        Radio.Station(
            id: 99, name: name ?? (seeds.first.map { "\($0.title) Radio" } ?? "\(feelings.prefix(3).joined(separator: " ")) Radio"),
            kind: .custom, frequency: 107.9, seeds: seeds, thumbnails: [], feelings: feelings,
            learning: true, exclusions: [], createdAt: .now
        )
    }
}
#endif
