import Foundation
import Observation

/// An artist's full catalog, one release category at a time, fetched a page at a time.
@MainActor @Observable
final class ArtistCatalogModel {
    typealias Fetch = @Sendable (ReleaseKind, Int) async throws -> CatalogReleasePage

    struct Section {
        var items: [CatalogAlbumSummary] = []
        var nextOffset: Int? = 0
        var isLoading = false
        var hasLoaded = false
        var error: String?
    }

    /// How close to the end of the list the next page starts loading.
    static let prefetchDistance = 5

    private(set) var kind: ReleaseKind = .albums
    private(set) var counts: [ReleaseKind: Int] = [:]
    private var sections: [ReleaseKind: Section] = [:]
    private let fetch: Fetch

    init(fetch: @escaping Fetch) { self.fetch = fetch }

    var current: Section { sections[kind] ?? Section() }

    /// Categories worth showing as filters: those with releases, plus the selected one. Albums and EPs come first.
    var visibleKinds: [ReleaseKind] {
        ReleaseKind.allCases.filter { $0 == kind || (counts[$0] ?? 0) > 0 }
    }

    func title(for kind: ReleaseKind) -> String {
        counts[kind].map { "\(kind.title) \($0)" } ?? kind.title
    }

    /// The loaded release with this catalog id, from any category.
    func release(pk: Int) -> CatalogAlbumSummary? {
        sections.values.lazy.compactMap { $0.items.first { $0.pk == pk } }.first
    }

    func start() async {
        guard !current.hasLoaded, !current.isLoading else { return }
        await loadNextPage(of: kind)
        if current.items.isEmpty, current.error == nil,
           let first = ReleaseKind.allCases.first(where: { (counts[$0] ?? 0) > 0 }) {
            await select(first)
        }
    }

    func select(_ newKind: ReleaseKind) async {
        kind = newKind
        if !current.hasLoaded { await loadNextPage(of: newKind) }
    }

    func loadMore(after item: CatalogAlbumSummary) async {
        let section = current
        guard section.nextOffset != nil, !section.isLoading,
              let index = section.items.firstIndex(where: { $0.pk == item.pk }),
              index >= section.items.count - Self.prefetchDistance else { return }
        await loadNextPage(of: kind)
    }

    func retry() async { await loadNextPage(of: kind) }

    private func loadNextPage(of target: ReleaseKind) async {
        var section = sections[target] ?? Section()
        guard let offset = section.nextOffset, !section.isLoading else { return }
        section.isLoading = true
        section.error = nil
        sections[target] = section
        do {
            let page = try await fetch(target, offset)
            var updated = sections[target] ?? Section()
            let known = Set(updated.items.map(\.pk))
            updated.items += page.results.filter { !known.contains($0.pk) }
            updated.nextOffset = page.results.isEmpty ? nil : page.nextOffset
            updated.hasLoaded = true
            updated.isLoading = false
            sections[target] = updated
            for (key, value) in page.counts {
                if let known = ReleaseKind(rawValue: key) { counts[known] = value }
            }
        } catch {
            var failed = sections[target] ?? Section()
            failed.isLoading = false
            failed.hasLoaded = true
            failed.error = (error as? LocalizedError)?.errorDescription ?? "The catalog couldn’t be loaded."
            sections[target] = failed
        }
    }
}
