import Foundation
import Observation
import SwiftData

@MainActor
@Observable
final class VibeAppModel {
    var session: JukeSession? {
        didSet { accessToken.set(session?.accessToken) }
    }
    var tab: JukeTab = .radio
    var banner: String?
    var messages: [ChatLine] = []
    var draft = ""
    var question = "What are you hearing differently right now?"
    var isSending = false
    var errorMessage: String?
    let nowPlaying = NowPlayingObserver()
    let atmosphere = VibeAtmosphere()

    /// Cross-section requests (New Station route, Library focus, station starts).
    let coordinator = JukeCoordinator()
    /// Typed client for the Juke REST API, authenticated as the signed-in user.
    let api: JukeAPI
    /// Radio stations, the tuned station and the continuous-play loop.
    let radio: RadioController
    let memories: MemoryStore
    /// Face ID / passcode lock over the whole app; shared with macOS.
    let lock = AppLockController()
    /// Quietly turns songs played elsewhere into `recognized` taste events.
    let recognition: BackgroundRecognizer
    /// `BackgroundRecognizer` holds its feed weakly, so the model owns it.
    @ObservationIgnored private let recognitionFeed: NowPlayingRecognitionFeed
    /// The song last started from Memories; recognition ignores it for a while.
    var memoryPlayback: MemoryPlaybackMark?
    /// Plays a memory's saved song and moment.
    let memoryPlayer: MemoryPlayer
    /// Previous / play-pause / next for the player shown on every tab.
    let transport: PlayerTransport
    /// Album-art colour feeding `JukeTheme`.
    let artwork = ArtworkPalette()
    /// DEBUG screenshots: pins the artwork colour (`--uitesting-artwork-hex=RRGGBB`).
    @ObservationIgnored private var artworkOverride: RGB?
    @ObservationIgnored private let accessToken = AccessTokenStore()
    private let context: ModelContext
    private let auth = JukeAuthService()
    private let vibe = VibeAPI()
    private let local = LocalVibeIntelligence()

    init(container: ModelContainer) {
        context = ModelContext(container)
        AppConfiguration.installLaunchFallback()
        let accessToken = accessToken
        api = JukeAPI(token: { accessToken.get() })
        #if DEBUG
        let fixtures = ProcessInfo.processInfo.arguments.contains("--uitesting")
        #else
        let fixtures = false
        #endif
        let store: MemoryStore
        if fixtures {
            #if DEBUG
            var samples: (@Sendable () async -> (memories: [MusicMemory], media: [(MemoryMedia, Data)]))?
            if ProcessInfo.processInfo.arguments.contains("--uitesting-memories-sample") {
                samples = { @Sendable in await MemorySampleData.make() }
            }
            let client = MemoryClient(fixtures: true, fixtureSamples: samples)
            #else
            let client = MemoryClient(fixtures: true)
            #endif
            store = MemoryStore(client: client)
        } else {
            store = MemoryStore()
        }
        memories = store
        recognitionFeed = NowPlayingRecognitionFeed(nowPlaying)
        recognition = .live(
            api: api,
            enabled: { UserDefaults.standard.object(forKey: JukeRecognitionSetting.key) as? Bool ?? true },
            token: { accessToken.get() },
            allowed: { !fixtures }
        )
        let saveMemory: @MainActor (MemoryDraft) async throws -> Void = { draft in _ = try await store.save(draft) }
        if fixtures {
            // Fresh in-memory radio and memories for UI checks; no network.
            let defaults = UserDefaults(suiteName: "juke.radio.uitests.\(UUID().uuidString)") ?? .standard
            let preferences = RadioPreferences(defaults: defaults)
            let scoped = preferences.scoped(to: JukeAccount.localPreview.id)
            scoped.hasTunedIn = !ProcessInfo.processInfo.arguments.contains("--uitesting-radio-first-run")
            scoped.wasPlaying = scoped.hasTunedIn
            scoped.recentRadioTrackIDs = [RadioFixturePlayback.initialTrackID]
            let playback = RadioFixturePlayback()
            radio = RadioController(backend: RadioFixtureBackend(playback: playback), playback: playback,
                                    preferences: preferences, coordinator: coordinator, saveMemory: saveMemory)
        } else {
            radio = RadioController(
                backend: api,
                playback: SpotifyRadioPlayback(token: { accessToken.get() }),
                coordinator: coordinator,
                saveMemory: saveMemory
            )
        }
        memoryPlayer = MemoryPlayer(token: { accessToken.get() })
        let nowPlaying = nowPlaying
        let memoryStore = memories
        let stepper = MemoryStepper(player: memoryPlayer, memories: { memoryStore.memories }, track: { nowPlaying.track })
        transport = PlayerTransport(radio: radio, memory: stepper, token: { accessToken.get() }, externalIsPlaying: { nowPlaying.isPlaying },
                                    externalSource: { TransportSource(trackSource: nowPlaying.track?.source) })
        memoryPlayer.marked = { [weak self] in self?.memoryPlayback = $0 }
        radio.onTrackChange = { [weak self] track in
            self?.radioTrackChanged(track)
            self?.recognition.noteRadioTrack(track?.spotifyId)
        }
        // Radio posts its own events, and a memory replay is not listening elsewhere.
        recognition.isRadioPlaying = { [weak radio] in (radio?.isOnAir ?? false) && (radio?.isPlaying ?? false) }
        recognition.isRadioTrack = { [weak radio] id in radio?.track?.spotifyId == id || radio?.queuedTrack?.spotifyId == id }
        recognition.memoryPlayback = { [weak self] in self?.memoryPlayback }
        recognition.follow(recognitionFeed)
        #if DEBUG
        if fixtures, ProcessInfo.processInfo.arguments.contains("--uitesting-authenticated") {
            let preview = JukeSession(account: .localPreview, accessToken: "ui-test-token", authenticatedAt: .now)
            session = preview
            if let name = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-tab=") })?.dropFirst(16), let value = JukeTab(rawValue: String(name)) { tab = value }
            if ProcessInfo.processInfo.arguments.contains("--uitesting-locked") { lock.lockNow() }
            beginSession(preview, polling: false)
            if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-new-station=") })?.dropFirst(24) {
                var draft = JukeCoordinator.NewStationDraft()
                draft.start = value == "feelings" ? .feelings : .records
                coordinator.openNewStation(draft)
            }
            if ProcessInfo.processInfo.arguments.contains("--uitesting-radio-putaway") {
                Task { try? await Task.sleep(for: .seconds(2)); await radio.putAway() }
            }
            // `--uitesting-radio-pause` pauses the song; `--uitesting-radio-resume` then presses play again
            // (with `--uitesting-radio-device-asleep` Spotify ignores it, as a suspended Spotify app does).
            let resumes = ProcessInfo.processInfo.arguments.contains("--uitesting-radio-resume")
            if resumes || ProcessInfo.processInfo.arguments.contains("--uitesting-radio-pause") {
                Task {
                    try? await Task.sleep(for: .seconds(2))
                    await radio.pause()
                    if resumes { try? await Task.sleep(for: .seconds(1)); await radio.resume() }
                }
            }
            // Screenshots of the player with radio off air: `--uitesting-now-playing=spotify|apple|aroundme`.
            if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-now-playing=") })?.dropFirst(24) {
                let source = ["apple": "Apple Music", "aroundme": "Shazam · Around Me"][String(value)] ?? "Spotify"
                nowPlaying.track = NowPlayingTrack(id: "ui-\(value)", title: "Blue in Green", artist: "Miles Davis", album: "Kind of Blue",
                                                   artworkURL: nil, localArtwork: nil, source: source)
            }
            if let hex = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-artwork-hex=") })?.dropFirst(24) {
                artworkOverride = RGB(hex: "#" + hex)
                artwork.apply(RGB(hex: "#" + hex))
            }
            return
        }
        #endif
        if let restored = try? auth.restore() {
            session = restored
            // A cold start is a fresh look at private chats and memories: ask first.
            lock.lockNow()
            beginSession(restored)
            Task { await synchronize(); load() }
        }
    }

    private func beginSession(_ value: JukeSession, polling: Bool = true) {
        accessToken.set(value.accessToken)
        if polling, let token = value.accessToken { nowPlaying.start(token: token) }
        recognition.reevaluate()
        Task {
            await memories.configure(session: value)
            await radio.start(accountID: value.account.id)
        }
    }

    private func radioTrackChanged(_ track: Radio.Track?) {
        if artworkOverride == nil { artwork.update(artworkURL: track?.artworkURL, enabled: atmosphere.enabled) }
        guard let track else { return }
        atmosphere.update(for: NowPlayingTrack(id: track.spotifyId, title: track.title, artist: track.artist, album: track.album, artworkURL: track.artworkURL, localArtwork: nil, source: "Juke Radio"))
    }

    /// The server changed in Settings: a token belongs to the server that issued it.
    func backendChanged() {
        guard session != nil else { return }
        logout()
        banner = "The Juke server changed. Sign in again to continue."
    }

    var trackLabel: String? { radio.isOnAir ? radio.track.map { "\($0.title) — \($0.artist)" } : nowPlaying.track?.label }

    func signIn(create: Bool = false) async {
        do {
            let value = try await auth.signIn(path: create ? "accounts/signup" : "accounts/login")
            session = value; beginSession(value); await synchronize(); load(); await refreshQuestion()
        } catch { errorMessage = error.localizedDescription }
    }

    func logout() { memoryPlayer.reset(); nowPlaying.stopPolling(); recognition.reset(); radio.stop(); memories.reset(); coordinator.reset(); auth.logout(); session = nil; messages = [] }

    func send() async {
        guard let session, let token = session.accessToken else { return }
        guard ChatComposer.canSend(draft: draft, isSending: isSending) else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        draft = ""; isSending = true; defer { isSending = false }
        do {
            try await store(text, role: "user")
            let reply = session.account.cloudAIEnabled
                ? try await vibe.chat(text, currentTrack: trackLabel, token: token)
                : try await local.respond(text, track: trackLabel, history: messages.map { "\($0.role): \($0.content)" })
            try await store(reply, role: "assistant")
        } catch { errorMessage = error.localizedDescription }
    }

    func trackChanged() {
        atmosphere.update(for: nowPlaying.track)
        if !radio.isOnAir, artworkOverride == nil { artwork.update(artworkURL: nowPlaying.track?.artworkURL, enabled: atmosphere.enabled) }
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
            do { try await vibe.upload(.init(recordID: id, accountID: accountID, kind: "chatMessage", ciphertext: sealed, modifiedAt: createdAt, encryptionVersion: 1), token: token) }
            catch { presentMessageSafetyNotice(accountID: accountID, token: token) }
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
            let incoming = try await vibe.encryptedChanges(token: token)
            let acknowledged = incoming.contains { $0.accountID == session.account.id && $0.kind == MessageSafetyNotice.recordKind }
            if acknowledged { MessageSafetyNotice.markShown(for: session.account.id) }
            else if MessageSafetyNotice.hasBeenShown(for: session.account.id) {
                await uploadMessageSafetyAcknowledgement(accountID: session.account.id, token: token)
            }
            let existing = try context.fetch(FetchDescriptor<EncryptedChatMessage>())
            let ids = Set(existing.map(\.id)); let vault = ChatVault(accountID: session.account.id)
            for envelope in incoming where !ids.contains(envelope.recordID) && envelope.accountID == session.account.id {
                guard envelope.kind == "chatMessage" else { continue }
                guard let payload = try? await vault.open(envelope.ciphertext, id: envelope.recordID) else { continue }
                context.insert(EncryptedChatMessage(id: envelope.recordID, accountID: envelope.accountID, role: payload.role, encryptedContent: envelope.ciphertext, trackIdentity: payload.trackIdentity, createdAt: payload.createdAt))
            }
            try context.save()
        } catch { }
    }

    private func presentMessageSafetyNotice(accountID: String, token: String) {
        guard MessageSafetyNotice.markShown(for: accountID) else { return }
        errorMessage = MessageSafetyNotice.message
        if !ProcessInfo.processInfo.arguments.contains("--uitesting") {
            Task { await uploadMessageSafetyAcknowledgement(accountID: accountID, token: token) }
        }
    }

    private func uploadMessageSafetyAcknowledgement(accountID: String, token: String) async {
        let id = MessageSafetyNotice.recordID(for: accountID)
        let createdAt = Date()
        let payload = PrivateChatPayload(role: "messageSafetyNotice", content: "shown", trackIdentity: nil, createdAt: createdAt)
        do {
            let ciphertext = try await ChatVault(accountID: accountID).seal(payload, id: id)
            try await vibe.upload(
                .init(recordID: id, accountID: accountID, kind: MessageSafetyNotice.recordKind, ciphertext: ciphertext, modifiedAt: createdAt, encryptionVersion: 1),
                token: token
            )
        } catch { /* The local per-account flag prevents repeats; the next session retries sync. */ }
    }
}
