import SwiftUI

struct RootView: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @State private var privacy = PrivacyWindow()
    @AppStorage("juke.settings.appearance") private var appearanceRaw = AppearanceChoice.system.rawValue
    var body: some View {
        ThemedRoot(content: content)
            .preferredColorScheme((AppearanceChoice(rawValue: appearanceRaw) ?? .system).colorScheme)
            .alert("Juke", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) { Button("OK") { model.errorMessage = nil } } message: { Text(model.errorMessage ?? "") }
    }

    private var content: some View {
        ZStack {
            VibeBackground(atmosphere: model.atmosphere)
            if model.session == nil { SignInView() } else { main.id(model.lock.isLocked) // a new identity dismisses open sheets, which would otherwise sit above the lock
                .disabled(model.lock.isLocked).accessibilityHidden(model.lock.isLocked) }
            if model.session != nil, model.lock.isLocked { LockedView() }
        }
        .onChange(of: scenePhase) { _, phase in
            privacy.update(shielded: PrivacyWindow.shouldShield(phase: phase, signedIn: model.session != nil))
            switch phase {
            case .active:
                model.lock.sceneBecameActive(isAuthenticated: model.session != nil)
                // Back from Spotify (or anywhere): catch up, and resume if the listener went to wake Spotify.
                Task { await model.radio.appBecameActive() }
            // Control Center and call banners only make the scene inactive; leaving the app is `.background`.
            case .background: model.lock.sceneBecameInactive()
            default: break
            }
        }
        .onChange(of: model.nowPlaying.track?.id) { _, _ in model.trackChanged() }
        // A failed Next or Previous is felt and, with VoiceOver, spoken, whichever tab is showing.
        .sensoryFeedback(.warning, trigger: model.radio.failedPresses)
        .onChange(of: model.radio.failedPresses) { _, _ in
            if let message = model.radio.issue?.message { AccessibilityNotification.Announcement(message).post() }
        }
    }

    private var main: some View {
        @Bindable var model = model
        return TabView(selection: $model.tab) {
            ForEach(JukeTab.allCases) { tab in
                // Every tab shows the artwork-tinted page, even screens with no background of their own.
                NavigationStack {
                    content(for: tab)
                        .scrollContentBackground(.hidden)
                        .containerBackground(for: .navigation) { VibeBackground(atmosphere: model.atmosphere) }
                }
                    .safeAreaInset(edge: .bottom) { if tab.showsMiniPlayer { MiniPlayerPill() } }
                    .tabItem { Label(tab.title, systemImage: tab.symbol) }
                    .tag(tab)
            }
        }
    }

    @ViewBuilder private func content(for tab: JukeTab) -> some View {
        switch tab {
        case .radio: RadioScreen()
        case .library: LibraryScreen()
        case .memories: MemoriesScreen()
        case .chat: ChatView()
        case .settings: SettingsView()
        }
    }
}

private struct LockedView: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        ZStack {
            Rectangle().fill(.regularMaterial).ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "lock.fill").font(.largeTitle).foregroundStyle(theme.ink.color)
                Text("Juke is locked").font(.title2.bold()).foregroundStyle(theme.ink.color)
                Button("Unlock") { Task { await model.lock.unlock() } }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .accessibilityIdentifier("lock.unlock")
                if let error = model.lock.unlockError {
                    Text(error).font(.footnote).foregroundStyle(theme.sub.color).multilineTextAlignment(.center)
                }
            }
            .padding(32)
        }
        .task { if model.lock.isLocked, model.lock.unlockError == nil, model.session != nil { await model.lock.unlock() } }
        .accessibilityIdentifier("lock.view")
    }
}

private struct SignInView: View {
    @Environment(VibeAppModel.self) private var model
    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "waveform.path.ecg.rectangle.fill").font(.system(size: 58)).foregroundStyle(model.atmosphere.primary)
            Text("Juke").font(.largeTitle.bold())
            Text("A private music companion that listens along.").font(.title3).padding(.horizontal, 24).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("Sign in with Juke") { Task { await model.signIn() } }.buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
            Button("Create an account") { Task { await model.signIn(create: true) } }
            if let banner = model.banner { Text(banner).font(.callout).foregroundStyle(.orange).multilineTextAlignment(.center) }
            Text("Conversation history is encrypted on this iPhone and is never uploaded as readable history.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).padding(.horizontal, 34)
            Spacer()
        }.padding()
    }
}

/// Builds the design-reference palette (light/dark plus the artwork colour) and
/// hands it to every screen through `\.jukeTheme`; the accent also tints controls.
private struct ThemedRoot<Content: View>: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let content: Content

    var body: some View {
        let theme = JukeTheme.palette(dark: scheme == .dark, base: model.artwork.base)
        content
            .environment(\.jukeTheme, theme)
            .tint(theme.accent.color)
            .onAppear { sync(theme) }
            .onChange(of: model.artwork.base) { _, _ in sync(JukeTheme.palette(dark: scheme == .dark, base: model.artwork.base)) }
            .onChange(of: scheme) { _, _ in sync(JukeTheme.palette(dark: scheme == .dark, base: model.artwork.base)) }
    }

    /// Screens that still read `atmosphere.primary` follow the themed accent.
    private func sync(_ theme: JukeTheme) {
        model.atmosphere.primary = theme.accent.color
        model.atmosphere.secondary = theme.card.color
    }
}
