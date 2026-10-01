import SwiftUI

/// The single Juke window: page background, header, the section stage and
/// the floating mini player. Builds the `JukeTheme` from the appearance and
/// the current artwork colour and injects it for every screen.
struct JukeRootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Follows `colorScheme`, but changes inside an animation so the palette
    /// cross-fades when the appearance changes.
    @State private var isDark: Bool?

    private var theme: JukeTheme {
        JukeTheme.palette(dark: isDark ?? (colorScheme == .dark), base: model.artwork.base)
    }

    var body: some View {
        ZStack {
            theme.bg.color.ignoresSafeArea()
            if model.session == nil {
                SignInView()
            } else {
                signedInContent
                    .disabled(model.lock.isLocked)
                    .accessibilityHidden(model.lock.isLocked)
            }
            if model.lock.isLocked, model.session != nil { LockedView() }
        }
        .foregroundStyle(theme.ink.color)
        .tint(theme.accent.color)
        .environment(\.jukeTheme, theme)
        .environment(model.memories)
        .environment(model.settings)
        .onChange(of: model.settings.appearance, initial: true) { _, choice in
            NSApplication.shared.appearance = choice.nsAppearance
        }
        .onChange(of: colorScheme, initial: true) { _, scheme in
            let dark = scheme == .dark
            guard isDark != nil else { isDark = dark; return }
            withAnimation(JukeMotion.colorCrossfade(reduceMotion: reduceMotion)) { isDark = dark }
        }
        .task(id: model.session?.accessToken) { await model.memories.configure(session: model.session) }
        .task(id: model.session?.account.id) { if model.session != nil { await model.radio.start() } }
        .onChange(of: scenePhase) { _, phase in
            let isActive = phase == .active
            model.detection.setApplicationActive(isActive)
            if isActive { model.lock.sceneBecameActive(isAuthenticated: model.session != nil) }
            else { model.lock.sceneBecameInactive() }
        }
        .onChange(of: model.detection.track?.identityKey) { _, _ in
            model.syncArtwork()
            Task { await model.refreshOpeningQuestion() }
        }
        .onChange(of: model.detection.track?.artworkURL) { _, _ in model.syncArtwork() }
        .onChange(of: model.settings.artworkTintEnabled) { _, _ in model.syncArtwork() }
        .task { await model.prepareUITestPresentationIfNeeded() }
        .alert("Juke", isPresented: Binding(get: { model.banner != nil }, set: { if !$0 { model.banner = nil } })) {
            Button("OK") { model.banner = nil }
        } message: { Text(model.banner ?? "") }
        .alert("Your conversations stay private", isPresented: Bindable(model).privacyWelcomePresented) {
            Button("Got it") { model.privacyWelcomePresented = false }
        } message: {
            Text("Juke encrypts conversation history before storing or syncing it. Cloud chat receives only the message you deliberately send and current-track context.")
        }
    }

    private var signedInContent: some View {
        let section = model.section
        let showsPill = section.showsMiniPlayer && !model.memoryJourneyActive
        return VStack(spacing: 0) {
            JukeHeader()
            SectionStage(selection: section) { shown in
                screen(for: shown)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.horizontal, JukeMetrics.headerHorizontalPadding)
            .padding(.bottom, section.showsMiniPlayer ? JukeMetrics.stageBottomPaddingWithPill : JukeMetrics.stageBottomPaddingRadio)
        }
        .overlay(alignment: .bottom) {
            if showsPill {
                MiniNowPlayingPill()
                    .padding(.bottom, JukeMetrics.miniPillBottomInset)
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .animation(JukeMotion.navigationIn(reduceMotion: reduceMotion), value: showsPill)
    }

    @ViewBuilder
    private func screen(for section: JukeSection) -> some View {
        switch section {
        case .radio: RadioScreen()
        case .library: LibraryScreen()
        case .memories: MemoriesScreen()
        case .chat: ChatScreen()
        }
    }
}

private struct SignInView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        JukeCard(padding: EdgeInsets(top: 48, leading: 56, bottom: 44, trailing: 56)) {
            VStack(spacing: 24) {
                VinylDisc(label: theme.accent.color, size: 96)
                VStack(spacing: 8) {
                    Text("juke")
                        .font(JukeFont.display(48, weight: .bold))
                        .tracking(-1)
                        .accessibilityLabel("Juke")
                    Text("Turn on the radio. Keep the songs. Remember the feeling.")
                        .font(JukeFont.body(17))
                        .foregroundStyle(theme.sub.color)
                        .multilineTextAlignment(.center)
                }
                HStack(spacing: 12) {
                    Button("Create a Juke account") { Task { await model.beginAuthentication(.createAccount) } }
                        .buttonStyle(JukeWellButtonStyle())
                        .accessibilityIdentifier("authentication.createAccount")
                    Button("Sign in") { Task { await model.beginAuthentication(.login) } }
                        .buttonStyle(JukeAccentButtonStyle())
                        .keyboardShortcut(.defaultAction)
                        .accessibilityIdentifier("authentication.signIn")
                }
                Text("Sign in to play radio, save songs, photos, videos and stories to your private music profile. Memories you submit are stored by Juke; conversation history stays encrypted.")
                    .font(JukeFont.body(13))
                    .foregroundStyle(theme.sub.color)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 430)
            }
        }
        .frame(maxWidth: 560)
        .padding(40)
    }
}

struct LockedView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        ZStack {
            theme.bg.color.opacity(0.92).ignoresSafeArea()
            Rectangle().fill(.ultraThinMaterial).ignoresSafeArea()
            JukeCard(padding: EdgeInsets(top: 32, leading: 40, bottom: 32, trailing: 40)) {
                VStack(spacing: 16) {
                    Image(systemName: "lock.fill").font(.largeTitle).foregroundStyle(theme.ink.color)
                    Text("Juke is locked").font(JukeFont.display(22))
                    Button("Unlock") { Task { await model.lock.unlock() } }
                        .buttonStyle(JukeAccentButtonStyle())
                        .keyboardShortcut(.defaultAction)
                    if let error = model.lock.unlockError {
                        Text(error).font(JukeFont.body(12)).foregroundStyle(theme.sub.color)
                    }
                }
            }
        }
    }
}
