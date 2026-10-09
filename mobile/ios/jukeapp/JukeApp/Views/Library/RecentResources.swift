import Foundation
import Observation

/// What the Library shows when nothing is searched: the listener's recent unique resources,
/// most recent first, topped up with recommendations while the history is short.
enum RecentLibrary {
    /// The most recent resources kept per kind.
    static let cap = 20
    /// Fewer recents than this are topped up with recommended ones.
    static let minimum = 10

    /// One resource is one (kind, Spotify id), however it was reached.
    static func key(_ item: Radio.CrateItem) -> String { "\(item.kind.rawValue):\(item.spotifyId)" }

    /// A stable identity, so the same resource keeps its row whether it came from history or from the fill.
    static func normalised(_ item: Radio.CrateItem) -> Radio.CrateItem {
        Radio.CrateItem(id: Radio.ID(key(item)), kind: item.kind, spotifyId: item.spotifyId, title: item.title,
                        subtitle: item.subtitle, artworkUrl: item.artworkUrl, track: item.track)
    }

    /// Puts `item` first, drops its earlier entry and keeps at most `cap` per kind.
    static func record(_ item: Radio.CrateItem, into recents: [Radio.CrateItem]) -> [Radio.CrateItem] {
        guard !item.spotifyId.isEmpty else { return recents }
        let new = normalised(item)
        var result = [new] + recents.filter { key($0) != key(new) }
        var seen: [Radio.SeedKind: Int] = [:]
        result = result.filter { entry in
            seen[entry.kind, default: 0] += 1
            return seen[entry.kind, default: 0] <= cap
        }
        return result
    }

    /// `kind`'s recents (up to `cap`), then `fill` (recommendations) that are not already there, up to `minimum`.
    static func library(kind: Radio.SeedKind, recents: [Radio.CrateItem], fill: [Radio.CrateItem]) -> [Radio.CrateItem] {
        var result: [Radio.CrateItem] = []
        var seen = Set<String>()
        for item in recents where item.kind == kind && seen.insert(key(item)).inserted && result.count < cap {
            result.append(normalised(item))
        }
        for item in fill where result.count < minimum && item.kind == kind && seen.insert(key(item)).inserted {
            result.append(normalised(item))
        }
        return result
    }
}

/// The recents on this device, per account. Searching for a resource, opening its screen or playing it records it.
@MainActor @Observable
final class RecentResources {
    private(set) var items: [Radio.CrateItem] = []
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private var scope = ""

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    private var storageKey: String { "juke.library.recents.\(scope)" }

    /// Switches to `accountID`'s history (nil on sign-out).
    func use(accountID: String?) {
        scope = accountID ?? ""
        guard accountID != nil, let data = defaults.data(forKey: storageKey),
              let saved = try? JSONDecoder().decode([Radio.CrateItem].self, from: data) else { items = []; return }
        items = saved
    }

    func record(_ item: Radio.CrateItem) {
        guard !scope.isEmpty else { return }
        items = RecentLibrary.record(item, into: items)
        if let data = try? JSONEncoder().encode(items) { defaults.set(data, forKey: storageKey) }
    }

    func record(kind: Radio.SeedKind, spotifyID: String, title: String, subtitle: String? = nil, artworkURL: String? = nil) {
        record(Radio.CrateItem(id: Radio.ID(spotifyID), kind: kind, spotifyId: spotifyID, title: title,
                               subtitle: subtitle, artworkUrl: artworkURL, track: nil))
    }

    /// A played song: the track's own details, artwork included.
    func record(track: Radio.Track) {
        record(kind: .track, spotifyID: track.spotifyId, title: track.title, subtitle: track.artist, artworkURL: track.artworkUrl)
    }
}
