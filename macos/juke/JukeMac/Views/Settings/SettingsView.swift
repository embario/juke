import SwiftUI

/// The Settings window (Command-,). Every preference lives in `JukeSettings`;
/// chat text size and the privacy lock keep their existing homes.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var colorScheme
    @State private var backendText = ""
    @State private var backendError: String?

    private var theme: JukeTheme { JukeTheme.palette(dark: colorScheme == .dark, base: model.artwork.base) }

    var body: some View {
        @Bindable var settings = model.settings
        Form {
            Section("Appearance") {
                Picker("Appearance", selection: $settings.appearance) {
                    ForEach(AppearanceChoice.allCases) { Label($0.label, systemImage: $0.symbol).tag($0) }
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("settings.appearance")
                Toggle("Tint the window with the album art", isOn: $settings.artworkTintEnabled)
                    .accessibilityIdentifier("settings.artworkTint")
                Text("Colours follow the current record and always keep text readable. Reduce Motion is respected.")
                    .font(.caption).foregroundStyle(theme.sub.color)
            }

            Section("Library") {
                Picker("Flip through the crate", selection: $settings.crateFlipDirection) {
                    ForEach(CrateFlipDirection.allCases) { Text($0.label).tag($0) }
                }
                .accessibilityIdentifier("settings.crateFlip")
            }

            Section("Listening") {
                Toggle("Recognize music in the background", isOn: $settings.backgroundRecognitionEnabled)
                    .accessibilityIdentifier("settings.backgroundRecognition")
                Picker("Listen with", selection: detectionMode) {
                    ForEach(MusicDetectionController.Mode.allCases) { mode in Text(mode.title).tag(mode) }
                }
                .disabled(model.session == nil)
                .accessibilityIdentifier("settings.detectionMode")
                Text("Juke notices what you play elsewhere to learn your taste. It reads Spotify and Apple Music; This Mac's Audio and Around Me use Shazam and ask for permission the first time. Juke never turns on the microphone unless you choose Around Me.")
                    .font(.caption).foregroundStyle(theme.sub.color)
            }

            Section("Chat") {
                HStack {
                    Text("Text size")
                    Slider(value: Bindable(model).chatTextSize, in: AppModel.chatTextSizeRange, step: 1)
                        .accessibilityIdentifier("settings.chatTextSize")
                    Text("\(Int(model.chatTextSize)) pt")
                        .monospacedDigit()
                        .foregroundStyle(theme.sub.color)
                        .frame(width: 42, alignment: .trailing)
                }
                Label("Chat is encrypted before it reaches local storage or Juke.", systemImage: "lock.shield")
                    .font(.caption)
            }

            Section("Privacy lock") {
                Picker("Lock after", selection: Bindable(model.lock).lockAfterMinutes) {
                    Text("Immediately").tag(0); Text("1 minute").tag(1); Text("5 minutes").tag(5); Text("15 minutes").tag(15)
                }
                Button("Lock now") { model.lock.lockNow() }
            }

            Section("Server") {
                HStack {
                    TextField("Juke server", text: $backendText, prompt: Text(JukeServer.defaultBaseURL.absoluteString))
                        .textFieldStyle(.roundedBorder)
                        .onSubmit(applyBackend)
                        .accessibilityIdentifier("settings.backendURL")
                    Button("Apply", action: applyBackend)
                        .disabled(JukeServer.normalizedBaseURL(backendText) == model.settings.backendURL)
                }
                if let backendError {
                    // Ink plus an icon: the accent colour is not AA-safe as text on every surface.
                    Label(backendError, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(theme.ink.color)
                        .accessibilityIdentifier("settings.backendURL.error")
                } else {
                    Text("Changing the server signs you out of this one.")
                        .font(.caption).foregroundStyle(theme.sub.color)
                }
                if model.settings.backendURL != JukeServer.defaultBaseURL {
                    Button("Use the default server") {
                        model.settings.resetBackendURL()
                        backendText = model.settings.backendURL.absoluteString
                        backendError = nil
                    }
                }
            }

            if let session = model.session {
                Section("Account") {
                    LabeledContent("Signed in as", value: session.account.displayName)
                    Button("Sign out", role: .destructive) { Task { await model.logout() } }
                        .accessibilityIdentifier("settings.signOut")
                }
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(theme.bg.color)
        .tint(theme.accent.color)
        .environment(\.jukeTheme, theme)
        .onAppear { backendText = model.settings.backendURL.absoluteString }
        .accessibilityIdentifier("settings.view")
        .navigationTitle("Juke Settings")
    }

    /// Switching the source is an explicit choice, so it applies at once;
    /// capture (and its permission prompt) starts only for This Mac or Around Me.
    private var detectionMode: Binding<MusicDetectionController.Mode> {
        Binding(
            get: { model.detection.mode },
            set: { mode in
                guard mode != model.detection.mode else { return }
                model.detection.mode = mode
                Task { await model.detection.start(token: model.session?.accessToken) }
            }
        )
    }

    private func applyBackend() {
        do {
            try model.settings.setBackendURL(backendText)
            backendText = model.settings.backendURL.absoluteString
            backendError = nil
        } catch {
            backendError = error.localizedDescription
        }
    }
}
