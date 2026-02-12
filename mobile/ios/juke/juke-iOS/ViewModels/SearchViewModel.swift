import Foundation
import JukeCore

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var query: String = ""
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var profileResults: [MusicProfileSummary] = []
    @Published private(set) var artists: [Artist] = []
    @Published private(set) var albums: [Album] = []
    @Published private(set) var tracks: [Track] = []
    @Published private(set) var errorMessage: String?

    private var searchTask: Task<Void, Never>?

    private let session: JukeSessionStore
    private let profileService: ProfileService
    private let catalogService: CatalogService

    init(
        session: JukeSessionStore,
        profileService: ProfileService = ProfileService(),
        catalogService: CatalogService = CatalogService()
    ) {
        self.session = session
        self.profileService = profileService
        self.catalogService = catalogService
    }

    func performSearch() {
        searchTask?.cancel()
        searchTask = Task {
            await search()
        }
    }

    private func search() async {
        let trimmedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let token = session.token else {
            errorMessage = "Log in to search the catalog."
            return
        }

        if trimmedQuery.isEmpty {
            self.profileResults = []
            self.artists = []
            self.albums = []
            self.tracks = []
            self.errorMessage = nil
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let profilesTask = profileService.searchProfiles(token: token, query: trimmedQuery)
            async let catalogTask = catalogService.fetchCatalog(token: token, query: trimmedQuery)
            let (profiles, catalog) = try await (profilesTask, catalogTask)
            profileResults = profiles
            artists = catalog.artists
            albums = catalog.albums
            tracks = catalog.tracks
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
