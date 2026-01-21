import SwiftUI

@MainActor
final class CreateSessionViewModel: ObservableObject {
    @Published var title = ""
    @Published var tracksPerPlayer = 3
    @Published var maxTracks = 30
    @Published var secondsPerTrack = 60
    @Published var transitionClip = "airhorn"
    @Published var hideTrackOwners = false
    @Published var isLoading = false
    @Published var errorMessage: String?

    static let transitionClips = [
        ("airhorn", "Air Horn"),
        ("buzzer", "Buzzer"),
        ("bell", "Bell"),
        ("whistle", "Whistle"),
        ("glass_clink", "Glass Clink"),
    ]

    private let sessionService: SessionService

    init(sessionService: SessionService = SessionService()) {
        self.sessionService = sessionService
    }

    func createSession(token: String?) async -> PowerHourSession? {
        guard let token else { return nil }

        let trimmed = title.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            errorMessage = "Session title is required."
            return nil
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let request = CreateSessionRequest(
            title: trimmed,
            tracksPerPlayer: tracksPerPlayer,
            maxTracks: maxTracks,
            secondsPerTrack: secondsPerTrack,
            transitionClip: transitionClip,
            hideTrackOwners: hideTrackOwners
        )

        do {
            return try await sessionService.createSession(request: request, token: token)
        } catch let error as APIError {
            errorMessage = error.errorDescription
            return nil
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}
