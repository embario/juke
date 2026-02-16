import SwiftUI
import JukeKit

@MainActor
final class AddTracksViewModel: ObservableObject {
    static let searchDebounceNanoseconds: UInt64 = 500_000_000

    @Published var searchQuery = ""
    @Published var searchResults: [CatalogTrack] = []
    @Published var isSearching = false
    @Published var addingTrackIds: Set<Int> = []
    @Published var addedTrackIds: Set<Int> = []
    @Published var errorMessage: String?

    let sessionId: String

    private let catalogService: CatalogService
    private let sessionService: SessionService
    private var searchTask: Task<Void, Never>?

    init(sessionId: String, catalogService: CatalogService = CatalogService(), sessionService: SessionService = SessionService()) {
        self.sessionId = sessionId
        self.catalogService = catalogService
        self.sessionService = sessionService
    }

    func search(token: String?) {
        searchTask?.cancel()

        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty, let token else {
            searchResults = []
            isSearching = false
            return
        }

        searchTask = Task {
            isSearching = true
            errorMessage = nil
            defer { isSearching = false }

            // Debounce
            try? await Task.sleep(nanoseconds: Self.searchDebounceNanoseconds)
            guard !Task.isCancelled else { return }

            do {
                let results = try await catalogService.searchTracks(query: query, token: token)
                guard !Task.isCancelled else { return }
                searchResults = results
                errorMessage = nil
            } catch {
                guard !Task.isCancelled else { return }
                errorMessage = (error as? JukeAPIError)?.localizedDescription ?? error.localizedDescription
            }
        }
    }

    func addTrack(_ track: CatalogTrack, token: String?) async {
        guard let token else { return }
        guard !addingTrackIds.contains(track.pk) && !addedTrackIds.contains(track.pk) else { return }

        addingTrackIds.insert(track.pk)
        errorMessage = nil

        do {
            _ = try await sessionService.addTrack(sessionId: sessionId, trackId: track.pk, token: token)
            addedTrackIds.insert(track.pk)
        } catch let error as JukeAPIError {
            errorMessage = error.localizedDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        addingTrackIds.remove(track.pk)
    }
}
