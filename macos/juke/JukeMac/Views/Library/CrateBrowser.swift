import Foundation
import Observation

/// State behind a crate: which kind of record, the "Dig for anything" query
/// (debounced into `GET radio/crate/?kind=&q=`), the loaded records and
/// which one is in front. Shared by Library and New Station.
@MainActor
@Observable
final class CrateBrowser {
    enum Phase: Equatable, Sendable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// Songs, Artists, Albums, in that order.
    static let kinds: [Radio.SeedKind] = [.track, .artist, .album]

    static func label(for kind: Radio.SeedKind) -> String {
        switch kind {
        case .artist: "Artists"
        case .album: "Albums"
        default: "Songs"
        }
    }

    private(set) var kind: Radio.SeedKind = .track
    /// The search text. Change it with `setQuery(_:)` so the search is debounced.
    private(set) var query = ""
    private(set) var items: [Radio.CrateItem] = []
    private(set) var phase: Phase = .idle
    /// Index of the record in front. Always within `items` (0 when empty).
    var focus = 0 {
        didSet {
            let clamped = CrateLayout.clamp(focus, count: items.count)
            if clamped != focus { focus = clamped }
        }
    }

    var focusedItem: Radio.CrateItem? { items.indices.contains(focus) ? items[focus] : nil }
    var trimmedQuery: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }

    @ObservationIgnored let source: any CrateSource
    @ObservationIgnored let debounce: Duration
    @ObservationIgnored private var searchTask: Task<Void, Never>?
    @ObservationIgnored private var generation = 0

    init(source: any CrateSource, debounce: Duration = .milliseconds(300)) {
        self.source = source
        self.debounce = debounce
    }

    /// Loads the personal crate once (the first time the crate is shown).
    func loadIfNeeded() async {
        guard phase == .idle else { return }
        await reload()
    }

    /// Switches Songs / Artists / Albums. Clears the search, like the prototype.
    func select(kind newKind: Radio.SeedKind) async {
        guard newKind != kind || !trimmedQuery.isEmpty else { return }
        kind = newKind
        query = ""
        await reload()
    }

    /// Updates the search text and loads results after the debounce.
    func setQuery(_ text: String) {
        guard text != query else { return }
        query = text
        searchTask?.cancel()
        let delay = debounce
        searchTask = Task { [weak self] in
            if delay > .zero {
                try? await Task.sleep(for: delay)
            }
            guard !Task.isCancelled else { return }
            await self?.reload()
        }
    }

    /// Waits for a pending debounced search (tests, and anything that needs the results).
    func settle() async {
        await searchTask?.value
    }

    /// Loads the current kind and query now. A newer request wins over an
    /// older one that finishes later.
    func reload() async {
        generation += 1
        let ticket = generation
        let kind = kind
        let query = trimmedQuery
        phase = .loading
        do {
            let loaded = try await source.crate(kind: kind, query: query.isEmpty ? nil : query)
            guard ticket == generation else { return }
            items = loaded
            // Start a little way into the personal crate so there are records on
            // both sides; search results start at the best match.
            focus = query.isEmpty ? min(2, max(0, loaded.count - 1)) : 0
            phase = .loaded
        } catch is CancellationError {
            if ticket == generation { phase = items.isEmpty ? .idle : .loaded }
        } catch {
            guard ticket == generation else { return }
            items = []
            focus = 0
            phase = .failed(error.localizedDescription)
        }
    }

    /// Moves focus by whole records (keyboard, wheel, VoiceOver).
    func step(_ delta: Int) {
        focus = CrateLayout.clamp(focus + delta, count: items.count)
    }

    // MARK: Bringing a record to the front

    /// Brings a record to the front: from the personal crate when it is there,
    /// otherwise by searching for its title.
    func reveal(kind targetKind: Radio.SeedKind, spotifyId: String, title: String) async {
        searchTask?.cancel()
        kind = targetKind == .unknown ? .track : targetKind
        // Without a Spotify id (a song playing outside radio) only the title can find it.
        let hasID = !spotifyId.isEmpty
        if hasID {
            if !trimmedQuery.isEmpty || phase != .loaded || items.first?.kind != kind {
                query = ""
                await reload()
            }
            if let index = index(of: spotifyId) {
                focus = index
                return
            }
        }
        query = title
        await reload()
        let byID = hasID ? index(of: spotifyId) : nil
        focus = byID ?? items.firstIndex { $0.title.localizedCaseInsensitiveCompare(title) == .orderedSame } ?? 0
    }

    func reveal(_ seed: Radio.Seed) async {
        await reveal(kind: seed.kind, spotifyId: seed.spotifyId, title: seed.title)
    }

    /// Consumes `coordinator.libraryFocus` (set by the radio sleeve's "Open the
    /// album/artist"), clearing it so it only applies once. Returns whether
    /// there was one.
    @discardableResult
    func consumeFocus(from coordinator: JukeCoordinator) async -> Bool {
        guard let target = coordinator.libraryFocus else { return false }
        coordinator.libraryFocus = nil
        await reveal(kind: target.kind, spotifyId: target.spotifyId, title: target.title)
        return true
    }

    private func index(of spotifyId: String) -> Int? {
        items.firstIndex { $0.spotifyId == spotifyId && $0.kind == kind } ?? items.firstIndex { $0.spotifyId == spotifyId }
    }
}
