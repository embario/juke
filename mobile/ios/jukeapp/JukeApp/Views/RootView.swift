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
        TabView {
            NavigationStack { ChatView().safeAreaInset(edge: .bottom) { NowPlayingPill() } }.tabItem { Label("Vibe", systemImage: "sparkles") }
            NavigationStack { DiscoverView().safeAreaInset(edge: .bottom) { NowPlayingPill() } }.tabItem { Label("Discover", systemImage: "safari") }
            NavigationStack { SettingsView() }.tabItem { Label("Settings", systemImage: "gearshape") }
        }.tint(model.atmosphere.primary)
    }
}

private struct SignInView: View {
    @Environment(VibeAppModel.self) private var model
    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "waveform.path.ecg.rectangle.fill").font(.system(size: 58)).foregroundStyle(model.atmosphere.primary)
            Text("Juke").font(.largeTitle.bold())
            Text("A private music companion that listens along.").font(.title3).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("Sign in with Juke") { Task { await model.signIn() } }.buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
            Button("Create an account") { Task { await model.signIn(create: true) } }
            Text("Conversation history is encrypted on this iPhone and is never uploaded as readable history.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).padding(.horizontal, 34)
            Spacer()
        }.padding()
    }
}
