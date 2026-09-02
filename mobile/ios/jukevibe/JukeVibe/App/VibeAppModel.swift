import Foundation
import Observation
import SwiftData

@MainActor
@Observable
final class VibeAppModel {
    var session: JukeSession?
    var messages: [ChatLine] = []
    var draft = ""
    var question = "What are you hearing differently right now?"
    var isSending = false
    var errorMessage: String?
    let nowPlaying = NowPlayingObserver()
    let atmosphere = VibeAtmosphere()

    private let context: ModelContext
    private let auth = JukeAuthService()
    private let api = VibeAPI()
    private let local = LocalVibeIntelligence()

    init(container: ModelContainer) {
        context = ModelContext(container)
        if let restored = try? auth.restore() { session = restored; Task { await synchronize(); load() }; if let token = restored.accessToken { nowPlaying.start(token: token) } }
    }

    var trackLabel: String? { nowPlaying.track?.label }

    func signIn(create: Bool = false) async {
        do {
            let value = try await auth.signIn(path: create ? "accounts/signup" : "accounts/login")
            session = value; await synchronize(); load(); if let token = value.accessToken { nowPlaying.start(token: token) }; await refreshQuestion()
        } catch { errorMessage = error.localizedDescription }
    }

    func logout() { nowPlaying.stopPolling(); auth.logout(); session = nil; messages = [] }

    func send() async {
        guard let session, let token = session.accessToken else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines); guard !text.isEmpty, !isSending else { return }
        draft = ""; isSending = true; defer { isSending = false }
        do {
            try await store(text, role: "user")
            let reply = session.account.cloudAIEnabled
                ? try await api.chat(text, currentTrack: trackLabel, token: token)
                : try await local.respond(text, track: trackLabel, history: messages.map { "\($0.role): \($0.content)" })
            try await store(reply, role: "assistant")
        } catch { errorMessage = error.localizedDescription }
    }

    func trackChanged() {
        atmosphere.update(for: nowPlaying.track)
        Task { await refreshQuestion() }
    }

    func refreshQuestion() async {
        if let value = try? await local.question(track: trackLabel, history: messages.map { "\($0.role): \($0.content)" }) { question = value }
    }

    private func store(_ text: String, role: String) async throws {
        guard let accountID = session?.account.id else { return }; let id = UUID(); let createdAt = Date()
        let payload = PrivateChatPayload(role: role, content: text, trackIdentity: trackLabel, createdAt: createdAt)
        let sealed = try await ChatVault(accountID: accountID).seal(payload, id: id)
        context.insert(EncryptedChatMessage(id: id, accountID: accountID, role: role, encryptedContent: sealed, trackIdentity: trackLabel, createdAt: createdAt)); try context.save()
        messages.append(ChatLine(id: id, role: role, content: text, createdAt: createdAt))
        if let token = session?.accessToken {
            do { try await api.upload(.init(recordID: id, accountID: accountID, kind: "chatMessage", ciphertext: sealed, modifiedAt: createdAt, encryptionVersion: 1), token: token) }
            catch { errorMessage = "This message is safe on this iPhone; encrypted sync will retry when Neptune is reachable." }
        }
    }

    private func load() {
        guard let accountID = session?.account.id else { return }
        let descriptor = FetchDescriptor<EncryptedChatMessage>(predicate: #Predicate { $0.accountID == accountID }, sortBy: [SortDescriptor(\.createdAt)])
        guard let records = try? context.fetch(descriptor) else { return }
        Task { var output: [ChatLine] = []; let vault = ChatVault(accountID: accountID)
            for record in records { if let value = try? await vault.open(record.encryptedContent, id: record.id) { output.append(ChatLine(id: record.id, role: record.role, content: value.content, createdAt: record.createdAt)) } }
            messages = output
        }
    }

    private func synchronize() async {
        guard let session, let token = session.accessToken else { return }
        do {
            let incoming = try await api.encryptedChanges(token: token)
            let existing = try context.fetch(FetchDescriptor<EncryptedChatMessage>())
            let ids = Set(existing.map(\.id)); let vault = ChatVault(accountID: session.account.id)
            for envelope in incoming where !ids.contains(envelope.recordID) && envelope.accountID == session.account.id {
                guard let payload = try? await vault.open(envelope.ciphertext, id: envelope.recordID) else { continue }
                context.insert(EncryptedChatMessage(id: envelope.recordID, accountID: envelope.accountID, role: payload.role, encryptedContent: envelope.ciphertext, trackIdentity: payload.trackIdentity, createdAt: payload.createdAt))
            }
            try context.save()
        } catch { }
    }
}
