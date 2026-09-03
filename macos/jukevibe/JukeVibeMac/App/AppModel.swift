import AppKit
import Foundation
import Observation
import SwiftData

struct DisplayChatMessage: Identifiable, Equatable {
    let id: UUID
    let role: ChatMessage.Role
    let content: String
    let createdAt: Date
}

@MainActor
@Observable
final class AppModel {
    static let chatTextSizeRange = 14.0...22.0
    static let defaultChatTextSize = 17.0

    enum Route: String, CaseIterable, Identifiable {
        case vibe, discover, library
        var id: String { rawValue }
        var title: String { rawValue.capitalized }
        var symbol: String {
            switch self { case .vibe: "sparkles"; case .discover: "safari"; case .library: "music.note.house" }
        }
    }

    var session: JukeSession?
    var route: Route = .vibe
    var messages: [DisplayChatMessage] = []
    var openingQuestion = "What are you hearing differently right now?"
    var draft = ""
    var isSending = false
    var isAwaitingReply = false
    var banner: String?
    var privacyWelcomePresented = false
    var chatTextSize = AppModel.defaultChatTextSize {
        didSet {
            let bounded = min(Self.chatTextSizeRange.upperBound, max(Self.chatTextSizeRange.lowerBound, chatTextSize))
            if bounded != chatTextSize { chatTextSize = bounded }
            UserDefaults.standard.set(bounded, forKey: Self.chatTextSizeKey)
        }
    }
    let lock = AppLockController()
    let detection = MusicDetectionController()
    let atmosphere = VisualAtmosphere()

    private let context: ModelContext
    private let auth = JukeAuthenticationService()
    private let neptune = NeptuneVibeClient()
    private let localIntelligence = LocalVibeIntelligence()
    private let isUITesting: Bool
    @ObservationIgnored private var replyTask: Task<Void, Never>?
    @ObservationIgnored private var chatVault: ChatVault?
    @ObservationIgnored private var chatVaultAccountID: String?
    nonisolated private static let chatTextSizeKey = "vibe.chatTextSize"

    init(container: ModelContainer) {
        let arguments = ProcessInfo.processInfo.arguments
        isUITesting = arguments.contains("--uitesting")
        context = ModelContext(container)
        let savedTextSize = UserDefaults.standard.object(forKey: Self.chatTextSizeKey) as? Double
        chatTextSize = min(
            Self.chatTextSizeRange.upperBound,
            max(Self.chatTextSizeRange.lowerBound, savedTextSize ?? Self.defaultChatTextSize)
        )
        if arguments.contains("--uitesting-authenticated") {
            session = JukeSession(
                account: .localPreview,
                accessToken: "ui-test-token",
                authenticatedAt: .now
            )
            detection.track = RecognizedTrack(
                title: "Blue in Green",
                artist: "Miles Davis",
                album: "Kind of Blue",
                isrc: "USSM15900122",
                artworkURL: nil,
                appleMusicURL: nil,
                shazamID: nil,
                providerNamespace: "apple_music",
                providerTrackID: "ui-test-blue-in-green"
            )
            detection.providerName = "Apple Music"
            detection.isAudioPresent = true
            detection.configureUITestPlayback(token: "ui-test-token")
            syncAtmosphere()
            if arguments.contains("--uitesting-reset-privacy-welcome") {
                UserDefaults.standard.removeObject(forKey: privacyWelcomeKey(accountID: JukeAccount.localPreview.id))
            }
        } else if !isUITesting {
            Task { await restoreSession() }
        }
    }

    func prepareUITestPresentationIfNeeded() async {
        let arguments = ProcessInfo.processInfo.arguments
        guard isUITesting, arguments.contains("--uitesting-show-privacy-welcome") else { return }
        try? await Task.sleep(for: .milliseconds(500))
        guard !Task.isCancelled else { return }
        presentPrivacyWelcomeIfNeeded()
    }

    var trackLabel: String? {
        guard let track = detection.track else { return nil }
        return "\(track.title) — \(track.artist)"
    }

    func beginAuthentication(_ destination: JukeAuthDestination) async {
        let url = await auth.browserURL(for: destination)
        NSWorkspace.shared.open(url)
    }

    func completeAuthentication(_ url: URL) async {
        do {
            session = try await auth.complete(callbackURL: url)
            presentPrivacyWelcomeIfNeeded()
            await synchronizeEncryptedHistory()
            loadMessages()
            await refreshOpeningQuestion()
            await detection.start(token: session?.accessToken)
        } catch { banner = error.localizedDescription }
    }

    func logout() async {
        replyTask?.cancel()
        replyTask = nil
        await detection.stop()
        do { try await auth.logout() } catch { banner = error.localizedDescription }
        session = nil
        messages = []
        chatVault = nil
        chatVaultAccountID = nil
        lock.lockNow()
    }

    func send() {
        guard let session, let token = session.accessToken else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        draft = ""
        isSending = true
        let currentTrack = trackLabel
        replyTask = Task { [weak self] in
            guard let self else { return }
            await self.completeSend(text: text, currentTrack: currentTrack, session: session, token: token)
        }
    }

    private func completeSend(text: String, currentTrack: String?, session: JukeSession, token: String) async {
        defer {
            isSending = false
            isAwaitingReply = false
            replyTask = nil
        }
        do {
            try await store(text, role: .user)
            isAwaitingReply = true
            let reply: String
            if isUITesting {
                // Leave enough time for macOS accessibility to observe the
                // transient typing state during an end-to-end test run.
                try await Task.sleep(for: .seconds(3))
                reply = "That muted trumpet opens a spacious conversation. What part of the performance draws you back in?"
            } else if session.account.cloudAIEnabled {
                reply = try await neptune.chat(message: text, currentTrack: currentTrack, token: token)
            } else {
                reply = try await localIntelligence.respond(
                    message: text,
                    currentTrack: currentTrack,
                    listenerName: session.account.displayName,
                    recentConversation: messages.map { "\($0.role.rawValue): \($0.content)" }
                )
            }
            try await store(reply, role: .assistant)
        } catch is CancellationError {
            return
        } catch {
            banner = error.localizedDescription
        }
    }

    func refreshOpeningQuestion() async {
        guard session != nil else { return }
        do {
            openingQuestion = try await localIntelligence.openingQuestion(
                currentTrack: trackLabel,
                listenerName: session?.account.displayName,
                recentConversation: messages.map { "\($0.role.rawValue): \($0.content)" }
            )
        } catch { }
    }

    func syncAtmosphere() {
        atmosphere.update(track: detection.track, isAudioPresent: detection.isAudioPresent)
    }

    private func restoreSession() async {
        do {
            session = try await auth.restoreSession()
            if session != nil {
                await synchronizeEncryptedHistory()
                loadMessages()
                await detection.start(token: session?.accessToken)
                await refreshOpeningQuestion()
            }
        } catch { banner = error.localizedDescription }
    }

    private func store(_ text: String, role: ChatMessage.Role) async throws {
        guard let accountID = session?.account.id else { return }
        let id = UUID()
        let createdAt = Date()
        let payload = PrivateChatPayload(role: role.rawValue, content: text, trackIdentity: trackLabel, createdAt: createdAt)
        let encrypted = try await vault(for: accountID).seal(payload, messageID: id)
        context.insert(ChatMessage(id: id, accountID: accountID, role: role, encryptedContent: encrypted, trackIdentity: trackLabel, createdAt: createdAt))
        try context.save()
        messages.append(DisplayChatMessage(id: id, role: role, content: text, createdAt: createdAt))
        if let token = session?.accessToken, !isUITesting {
            let envelope = NeptuneVibeClient.EncryptedEnvelope(recordID: id, accountID: accountID, kind: "chatMessage", ciphertext: encrypted, modifiedAt: createdAt, encryptionVersion: 1)
            Task { [weak self] in
                guard let self else { return }
                do {
                    try await neptune.upload(envelope, token: token)
                } catch {
                    // The encrypted local record remains canonical while sync is unavailable.
                }
            }
        }
    }

    private func loadMessages() {
        guard let accountID = session?.account.id else { return }
        let descriptor = FetchDescriptor<ChatMessage>(
            predicate: #Predicate { $0.accountID == accountID },
            sortBy: [SortDescriptor(\.createdAt)]
        )
        do {
            let records = try context.fetch(descriptor)
            Task {
                let vault = vault(for: accountID)
                var output: [DisplayChatMessage] = []
                for record in records {
                    if let payload = try? await vault.open(record.encryptedContent, messageID: record.id),
                       let role = ChatMessage.Role(rawValue: record.roleRawValue) {
                        output.append(DisplayChatMessage(id: record.id, role: role, content: payload.content, createdAt: record.createdAt))
                    }
                }
                messages = output
            }
        } catch { banner = "Your private conversations could not be opened." }
    }

    private func synchronizeEncryptedHistory() async {
        guard let session, let token = session.accessToken else { return }
        do {
            let incoming = try await neptune.encryptedChanges(token: token)
            let existing = try context.fetch(FetchDescriptor<ChatMessage>())
            let ids = Set(existing.map(\.id))
            let vault = vault(for: session.account.id)
            for envelope in incoming where !ids.contains(envelope.recordID) && envelope.accountID == session.account.id {
                guard let payload = try? await vault.open(envelope.ciphertext, messageID: envelope.recordID),
                      let role = ChatMessage.Role(rawValue: payload.role) else { continue }
                context.insert(ChatMessage(id: envelope.recordID, accountID: envelope.accountID, role: role, encryptedContent: envelope.ciphertext, trackIdentity: payload.trackIdentity, createdAt: payload.createdAt))
            }
            try context.save()
        } catch { }
    }

    private func presentPrivacyWelcomeIfNeeded() {
        guard let accountID = session?.account.id else { return }
        let key = privacyWelcomeKey(accountID: accountID)
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        UserDefaults.standard.set(true, forKey: key)
        privacyWelcomePresented = true
    }

    private func privacyWelcomeKey(accountID: String) -> String {
        "vibe.encryptionWelcomeSeen.\(accountID)"
    }

    func play(_ result: CatalogSearchResult, kind: String) async {
        guard detection.canStartSpotifyPlayback else {
            banner = "Spotify playback is not connected. You can still browse and listen along in spectator mode."
            return
        }
        guard let spotifyID = result.spotifyID else {
            banner = "This catalog result does not have a playable Spotify reference yet."
            return
        }
        await detection.playSpotify(
            id: spotifyID,
            kind: kind,
            optimisticTrack: kind == "tracks" ? result.recognizedTrack : nil
        )
    }

    func play(_ track: CatalogTrackDetail, albumName: String, artistName: String? = nil) async {
        guard detection.canStartSpotifyPlayback else {
            banner = "Spotify playback is not connected. You can still browse and listen along in spectator mode."
            return
        }
        guard let spotifyID = track.spotifyID else {
            banner = "This track does not have a playable Spotify reference yet."
            return
        }
        await detection.playSpotify(
            id: spotifyID,
            kind: "tracks",
            optimisticTrack: RecognizedTrack(
                title: track.name,
                artist: artistName ?? "Juke catalog",
                album: albumName,
                isrc: nil,
                artworkURL: nil,
                appleMusicURL: nil,
                shazamID: nil,
                trackDuration: track.durationMs.map { TimeInterval($0) / 1_000 },
                providerNamespace: "spotify",
                providerTrackID: spotifyID
            )
        )
    }

    func useSpotifySpectatorMode() {
        detection.useSpotifySpectatorMode()
    }

    func useSpotifyPlaybackMode() {
        let needsConnection = !detection.hasVerifiedSpotifyPlayback
        detection.useSpotifyPlaybackMode()
        if needsConnection { openSpotifyConnection() }
    }

    func openSpotifyConnection() {
        guard let token = session?.accessToken,
              let url = JukeAuthenticationService.spotifyConnectionURL(token: token) else {
            banner = "Sign in to Juke before connecting Spotify."
            return
        }
        if isUITesting {
            banner = "Spotify connection would open in Juke."
        } else {
            NSWorkspace.shared.open(url)
        }
    }

    private func vault(for accountID: String) -> ChatVault {
        if chatVaultAccountID != accountID || chatVault == nil {
            chatVault = ChatVault(accountID: accountID)
            chatVaultAccountID = accountID
        }
        return chatVault!
    }

}
