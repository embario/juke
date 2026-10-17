import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct ArtistCatalogModelTests {
    private nonisolated static func album(_ pk: Int) -> CatalogAlbumSummary {
        try! JSONDecoder().decode(CatalogAlbumSummary.self, from: Data(#"{"pk":\#(pk),"name":"Release \#(pk)","spotify_id":"id\#(pk)","release_date":"2001-01-01"}"#.utf8))
    }

    private nonisolated static func page(_ pks: [Int], next: Int?, total: Int, counts: [String: Int] = [:]) -> CatalogReleasePage {
        CatalogReleasePage(count: total, nextOffset: next, counts: counts, results: pks.map(Self.album))
    }

    /// Records every (kind, offset) request and answers from a script.
    final class Backend: @unchecked Sendable {
        private let lock = NSLock()
        private var _calls: [String] = []
        var calls: [String] { lock.withLock { _calls } }
        let answer: @Sendable (ReleaseKind, Int) throws -> CatalogReleasePage
        init(_ answer: @escaping @Sendable (ReleaseKind, Int) throws -> CatalogReleasePage) { self.answer = answer }
        func fetch(_ kind: ReleaseKind, _ offset: Int) async throws -> CatalogReleasePage {
            lock.withLock { _calls.append("\(kind.rawValue)@\(offset)") }
            return try answer(kind, offset)
        }
    }

    private struct Failure: LocalizedError { var errorDescription: String? { "boom" } }

    @Test func albumsAndEPsComeFirstAndEmptyCategoriesAreHidden() async {
        let counts = ["albums": 3, "eps": 1, "singles": 0, "compilations": 2, "live": 0, "appearances": 4]
        let backend = Backend { _, _ in Self.page([1], next: nil, total: 3, counts: counts) }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        #expect(model.visibleKinds == [.albums, .eps, .compilations, .appearances])
        #expect(model.title(for: .eps) == "EPs 1")
    }

    @Test func scrollingNearTheEndLoadsEveryProviderPageOnce() async {
        let backend = Backend { _, offset in
            Self.page(Array(offset..<min(offset + 10, 25)).map { $0 + 1 }, next: offset + 10 < 25 ? offset + 10 : nil, total: 25)
        }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        #expect(model.current.items.count == 10)
        await model.loadMore(after: model.current.items[0])
        #expect(model.current.items.count == 10, "the first row is nowhere near the end")
        await model.loadMore(after: model.current.items[5])
        await model.loadMore(after: model.current.items[15])
        #expect(model.current.items.map(\.pk) == Array(1...25))
        #expect(model.current.nextOffset == nil)
        await model.loadMore(after: model.current.items[24])
        #expect(backend.calls == ["albums@0", "albums@10", "albums@20"], "no request after the last page")
    }

    @Test func duplicatePagesDoNotRepeatRows() async {
        let backend = Backend { _, offset in
            offset == 0 ? Self.page([1, 2], next: 2, total: 3) : Self.page([2, 3], next: nil, total: 3)
        }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        await model.loadMore(after: model.current.items[1])
        #expect(model.current.items.map(\.pk) == [1, 2, 3])
    }

    @Test func eachCategoryKeepsItsOwnPagesAndOffsets() async {
        let backend = Backend { kind, offset in
            kind == .albums ? Self.page([1, 2], next: 2, total: 4) : Self.page([100], next: nil, total: 1)
        }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        await model.select(.eps)
        #expect(model.current.items.map(\.pk) == [100])
        await model.select(.albums)
        #expect(model.current.items.map(\.pk) == [1, 2], "switching back does not refetch")
        await model.select(.eps)
        #expect(backend.calls == ["albums@0", "eps@0"])
    }

    @Test func anArtistWithoutAlbumsOpensOnTheFirstCategoryThatHasReleases() async {
        let backend = Backend { kind, _ in
            kind == .albums
                ? Self.page([], next: nil, total: 0, counts: ["albums": 0, "singles": 2])
                : Self.page([7, 8], next: nil, total: 2, counts: ["albums": 0, "singles": 2])
        }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        #expect(model.kind == .singles)
        #expect(model.current.items.map(\.pk) == [7, 8])
    }

    @Test func aFailedPageIsRetryableAndKeepsWhatWasLoaded() async {
        let failOnce = Once()
        let flaky = Backend { _, offset in
            if offset == 2 && failOnce.take() { throw Failure() }
            return Self.page(offset == 0 ? [1, 2] : [3], next: offset == 0 ? 2 : nil, total: 3)
        }
        let model = ArtistCatalogModel(fetch: flaky.fetch)
        await model.start()
        await model.loadMore(after: model.current.items[1])
        #expect(model.current.error == "boom")
        #expect(model.current.items.map(\.pk) == [1, 2])
        await model.retry()
        #expect(model.current.error == nil)
        #expect(model.current.items.map(\.pk) == [1, 2, 3])
    }

    private final class Once: @unchecked Sendable {
        private let lock = NSLock()
        private var armed = true
        func take() -> Bool { lock.withLock { defer { armed = false }; return armed } }
    }

    @Test func releasesAreLookedUpAcrossCategories() async {
        let backend = Backend { kind, _ in
            Self.page(kind == .albums ? [1] : [2], next: nil, total: 1, counts: ["albums": 1, "eps": 1])
        }
        let model = ArtistCatalogModel(fetch: backend.fetch)
        await model.start()
        await model.select(.eps)
        #expect(model.release(pk: 1)?.name == "Release 1")
        #expect(model.release(pk: 2)?.name == "Release 2")
        #expect(model.release(pk: 3) == nil)
    }

    @Test func releasePageDecodesTheBackendPayload() throws {
        let json = #"{"count":2,"next_offset":null,"counts":{"albums":2,"eps":0},"synced":false,"results":[{"pk":1,"name":"A","spotify_id":"a","spotify_data":{"images":["https://i/a.jpg"]},"total_tracks":9,"release_date":"2020-01-01"}]}"#
        let page = try JSONDecoder().decode(CatalogReleasePage.self, from: Data(json.utf8))
        #expect(page.count == 2 && page.nextOffset == nil && page.synced == false)
        #expect(page.counts["albums"] == 2)
        #expect(page.results.first?.artworkURL?.absoluteString == "https://i/a.jpg")
    }
}
