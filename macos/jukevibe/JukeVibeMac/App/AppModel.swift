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
    var banner: String?
    var settingsPresented = false
    let lock = AppLockController()
    let detection = MusicDetectionController()
    let atmosphere = VisualAtmosphere()

    private let context: ModelContext
    private let auth = JukeAuthenticationService()
    private let neptune = NeptuneVibeClient()
    private let localIntelligence = LocalVibeIntelligence()

    init(container: ModelContainer) {
        context = ModelContext(container)
        Task { await restoreSession() }
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
            await synchronizeEncryptedHistory()
            loadMessages()
            await refreshOpeningQuestion()
            await detection.start()
        } catch { banner = error.localizedDescription }
    }

    func logout() async {
        await detection.stop()
        do { try await auth.logout() } catch { banner = error.localizedDescription }
        session = nil
        messages = []
        lock.lockNow()
    }

    func send() async {
        guard let session, let token = session.accessToken else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        draft = ""
        isSending = true
        defer { isSending = false }
        do {
            try await store(text, role: .user)
            let reply: String
            if session.account.cloudAIEnabled {
                reply = try await neptune.chat(message: text, currentTrack: trackLabel, token: token)
            } else {
                reply = try await localIntelligence.respond(
                    message: text,
                    currentTrack: trackLabel,
                    recentConversation: messages.map { "\($0.role.rawValue): \($0.content)" }
                )
            }
            try await store(reply, role: .assistant)
        } catch { banner = error.localizedDescription }
    }

    func refreshOpeningQuestion() async {
        guard session != nil else { return }
        do {
            openingQuestion = try await localIntelligence.openingQuestion(
                currentTrack: trackLabel,
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
                await detection.start()
                await refreshOpeningQuestion()
            }
        } catch { banner = error.localizedDescription }
    }

    private func store(_ text: String, role: ChatMessage.Role) async throws {
        guard let accountID = session?.account.id else { return }
        let id = UUID()
        let createdAt = Date()
        let payload = PrivateChatPayload(role: role.rawValue, content: text, trackIdentity: trackLabel, createdAt: createdAt)
        let encrypted = try await ChatVault(accountID: accountID).seal(payload, messageID: id)
        context.insert(ChatMessage(id: id, accountID: accountID, role: role, encryptedContent: encrypted, trackIdentity: trackLabel, createdAt: createdAt))
        try context.save()
        messages.append(DisplayChatMessage(id: id, role: role, content: text, createdAt: createdAt))
        if let token = session?.accessToken {
            let envelope = NeptuneVibeClient.EncryptedEnvelope(recordID: id, accountID: accountID, kind: "chatMessage", ciphertext: encrypted, modifiedAt: createdAt, encryptionVersion: 1)
            do { try await neptune.upload(envelope, token: token) }
            catch { banner = "This message is safe on this Mac; encrypted sync will retry when Neptune is reachable." }
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
                let vault = ChatVault(accountID: accountID)
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
            let vault = ChatVault(accountID: session.account.id)
            for envelope in incoming where !ids.contains(envelope.recordID) && envelope.accountID == session.account.id {
                guard let payload = try? await vault.open(envelope.ciphertext, messageID: envelope.recordID),
                      let role = ChatMessage.Role(rawValue: payload.role) else { continue }
                context.insert(ChatMessage(id: envelope.recordID, accountID: envelope.accountID, role: role, encryptedContent: envelope.ciphertext, trackIdentity: payload.trackIdentity, createdAt: payload.createdAt))
            }
            try context.save()
        } catch { }
    }

}
