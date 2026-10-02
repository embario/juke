import SwiftUI

struct SettingsView: View {
    @Environment(VibeAppModel.self) private var model
    var body: some View {
        Form {
            Section("Visual atmosphere") {
                Toggle("Respond to the music", isOn: Bindable(model.atmosphere).enabled)
                Text("Current artwork shapes the colors. Motion follows your Accessibility settings.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Music detection") {
                LabeledContent("Apple Music", value: "On while active")
                LabeledContent("Spotify", value: "Through Juke")
                Toggle("Identify Around Me", isOn: Binding(get: { model.nowPlaying.isListeningAroundMe }, set: { enabled in Task { await model.nowPlaying.setAroundMe(enabled) } }))
                Text("iOS does not expose a universal queue or another app's raw audio. Juke reads Apple Music's current item, checks linked Spotify playback through Neptune, and uses the microphone only when you enable Around Me.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Conversation privacy") {
                Label("Encrypted before local storage", systemImage: "lock.shield")
                Text("Past chat stays private on your devices. A cloud model receives only text you deliberately submit for that reply.").font(.caption).foregroundStyle(.secondary)
            }
            Section { Button("Log out", role: .destructive) { model.logout() } }
        }.scrollContentBackground(.hidden).background(VibeBackground(atmosphere: model.atmosphere)).navigationTitle("Settings")
    }
}
