import SwiftUI

struct RootView: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        ZStack {
            VibeBackground(atmosphere: model.atmosphere)
            if model.session == nil { SignInView() } else { main }
        }
        .onChange(of: model.nowPlaying.track?.id) { _, _ in model.trackChanged() }
        .alert("Juke", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) { Button("OK") { model.errorMessage = nil } } message: { Text(model.errorMessage ?? "") }
    }

    private var main: some View {
        @Bindable var model = model
        return TabView(selection: $model.tab) {
            ForEach(JukeTab.allCases) { tab in
                NavigationStack { content(for: tab) }
                    .safeAreaInset(edge: .bottom) { if tab != .radio { MiniPlayerPill() } }
                    .tabItem { Label(tab.title, systemImage: tab.symbol) }
                    .tag(tab)
            }
        }.tint(model.atmosphere.primary)
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
