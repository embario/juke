import SwiftUI

struct SettingsView: View {
    @Environment(VibeAppModel.self) private var model
    @State private var serverText = ""
    @State private var serverError: String?
    @State private var loaded = false

    var body: some View {
        Form {
            Section {
                TextField("https://neptune.tail647b75.ts.net", text: $serverText)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .onSubmit(saveServer)
                if let serverError { Text(serverError).font(.caption).foregroundStyle(.red) }
                HStack {
                    Button("Use default") { serverText = ""; saveServer() }
                    Spacer()
                    Button("Save", action: saveServer)
                }
            } header: { Text("Juke server") } footer: {
                Text("HTTPS is required (plain HTTP only for localhost). Changing the server signs you out, because a sign-in belongs to the server that issued it.")
            }
            Section("Visual atmosphere") {
                Toggle("Respond to the music", isOn: Bindable(model.atmosphere).enabled)
                Text("Current artwork shapes the colors. Motion follows your Accessibility settings.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Music detection") {
                LabeledContent("Radio", value: "Spotify through Juke")
                LabeledContent("Apple Music", value: "On while active")
                Toggle("Identify Around Me", isOn: Binding(get: { model.nowPlaying.isListeningAroundMe }, set: { enabled in Task { await model.nowPlaying.setAroundMe(enabled) } }))
                Text("iOS does not expose a universal queue or another app's raw audio. Juke reads Apple Music's current item, checks linked Spotify playback through Juke, and uses the microphone only when you enable Around Me.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Conversation privacy") {
                Label("Encrypted before local storage", systemImage: "lock.shield")
                Text("Past chat stays private on your devices. A cloud model receives only text you deliberately submit for that reply.").font(.caption).foregroundStyle(.secondary)
            }
            Section {
                if let account = model.session?.account { LabeledContent("Signed in as", value: account.displayName) }
                Button("Log out", role: .destructive) { model.logout() }
            }
        }
        .scrollContentBackground(.hidden).background(VibeBackground(atmosphere: model.atmosphere)).navigationTitle("Settings")
        .onAppear {
            guard !loaded else { return }
            loaded = true
            serverText = UserDefaults.standard.string(forKey: JukeServer.backendURLKey) ?? ""
        }
    }

    private func saveServer() {
        let text = serverText.trimmingCharacters(in: .whitespacesAndNewlines)
        let previous = JukeServer.baseURL()
        if text.isEmpty {
            UserDefaults.standard.removeObject(forKey: JukeServer.backendURLKey)
            serverError = nil
        } else if let url = JukeServer.normalizedBaseURL(text) {
            UserDefaults.standard.set(url.absoluteString, forKey: JukeServer.backendURLKey)
            serverText = url.absoluteString; serverError = nil
        } else {
            serverError = "Enter an https:// address (http only for localhost)."
            return
        }
        if JukeServer.baseURL() != previous { model.backendChanged() }
    }
}
