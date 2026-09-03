import SwiftUI

struct JukeVibeRootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        ZStack {
            VibeAtmosphereBackground(atmosphere: model.atmosphere)
            if model.session == nil { SignInView() } else { signedInContent }
            if model.lock.isLocked, model.session != nil { LockedView() }
        }
        .onChange(of: scenePhase) { _, phase in
            let isActive = phase == .active
            model.detection.setApplicationActive(isActive)
            if isActive { model.lock.sceneBecameActive(isAuthenticated: model.session != nil) }
            else { model.lock.sceneBecameInactive() }
        }
        .onChange(of: model.detection.track?.identityKey) { _, _ in
            model.syncAtmosphere()
            Task { await model.refreshOpeningQuestion() }
        }
        .onChange(of: model.detection.isAudioPresent) { _, _ in model.syncAtmosphere() }
        .onChange(of: model.atmosphere.isEnabled) { _, _ in model.syncAtmosphere() }
        .task { await model.prepareUITestPresentationIfNeeded() }
        .alert("Juke Vibe", isPresented: Binding(get: { model.banner != nil }, set: { if !$0 { model.banner = nil } })) {
            Button("OK") { model.banner = nil }
        } message: { Text(model.banner ?? "") }
        .alert("Your conversations stay private", isPresented: Bindable(model).privacyWelcomePresented) {
            Button("Got it") { model.privacyWelcomePresented = false }
        } message: {
            Text("Juke Vibe encrypts conversation history before storing or syncing it. Cloud chat receives only the message you deliberately send and current-track context.")
        }
    }

    private var signedInContent: some View {
        NavigationSplitView {
            VStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("JUKE").font(.caption.weight(.bold)).tracking(2.5).foregroundStyle(.secondary)
                    Text("Vibe").font(.system(size: 28, weight: .semibold, design: .rounded))
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 6)

                ForEach(AppModel.Route.allCases) { route in
                    Button { withAnimation(.snappy) { model.route = route } } label: {
                        Label(route.title, systemImage: route.symbol).frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 7)
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 10)
                    .background(model.route == route ? model.atmosphere.primary.opacity(0.18) : .clear, in: RoundedRectangle(cornerRadius: 11))
                    .accessibilityIdentifier("sidebar.\(route.rawValue)")
                }
                Spacer()
                SettingsLink {
                    Label("Settings", systemImage: "gearshape").frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("sidebar.settings")
                Button(role: .destructive) { Task { await model.logout() } } label: {
                    Label("Log out", systemImage: "rectangle.portrait.and.arrow.right").frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain)
            }
            .padding(18)
            .navigationSplitViewColumnWidth(min: 180, ideal: 210, max: 240)
            .background(.ultraThinMaterial)
        } detail: {
            VStack(spacing: 0) {
                Group {
                    switch model.route {
                    case .vibe: VibeChatView()
                    case .discover: DiscoverView()
                    case .library: PrivateListeningLibraryView()
                    }
                }
                NowPlayingBar()
            }
        }
    }
}

private struct SignInView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "waveform.path.ecg.rectangle.fill").font(.system(size: 56)).foregroundStyle(model.atmosphere.primary)
            VStack(spacing: 8) {
                Text("Juke Vibe").font(.system(size: 42, weight: .semibold, design: .rounded))
                Text("A private, perceptive companion for wherever music takes you.").font(.title3).foregroundStyle(.secondary)
            }
            HStack {
                Button("Create a Juke account") { Task { await model.beginAuthentication(.createAccount) } }
                    .accessibilityIdentifier("authentication.createAccount")
                Button("Sign in") { Task { await model.beginAuthentication(.login) } }
                    .buttonStyle(.borderedProminent)
                    .tint(model.atmosphere.primary)
                    .accessibilityIdentifier("authentication.signIn")
            }
            Text("Conversation history is encrypted on this Mac. Juke never receives that history unless you explicitly submit text for an AI reply.")
                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 430)
        }.padding(54)
    }
}

private struct LockedView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        ZStack {
            Rectangle().fill(.ultraThickMaterial).ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "lock.fill").font(.largeTitle)
                Text("Juke Vibe is locked").font(.title2.weight(.semibold))
                Button("Unlock") { Task { await model.lock.unlock() } }.buttonStyle(.borderedProminent).tint(model.atmosphere.primary)
                if let error = model.lock.unlockError { Text(error).font(.caption).foregroundStyle(.secondary) }
            }
        }
    }
}
