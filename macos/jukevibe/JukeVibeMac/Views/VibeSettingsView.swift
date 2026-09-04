import SwiftUI

struct VibeSettingsView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        ZStack {
            VibeAtmosphereBackground(atmosphere: model.atmosphere)
            Form {
                Section("Visual atmosphere") {
                    Toggle("Let the interface respond to the music", isOn: Bindable(model.atmosphere).isEnabled)
                    Text("Artwork shapes the palette; active audio gently raises the visual intensity. Reduce Motion is always respected.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Chat appearance") {
                    HStack {
                        Text("Text size")
                        Slider(
                            value: Bindable(model).chatTextSize,
                            in: AppModel.chatTextSizeRange,
                            step: 1
                        )
                        .accessibilityIdentifier("settings.chatTextSize")
                        Text("\(Int(model.chatTextSize)) pt")
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                            .frame(width: 42, alignment: .trailing)
                    }
                    Text("Juke keeps chat text between 14 and 22 points so conversations remain readable without crowding the window.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Privacy lock") {
                    Picker("Lock after", selection: Bindable(model.lock).lockAfterMinutes) {
                        Text("Immediately").tag(0); Text("1 minute").tag(1); Text("5 minutes").tag(5); Text("15 minutes").tag(15)
                    }
                    Button("Lock now") { model.lock.lockNow() }
                }
                Section("Conversation privacy") {
                    Label("Chat is encrypted before it reaches local storage.", systemImage: "lock.shield")
                    Text("Past conversation stays on your devices. Cloud chat receives only the message you deliberately send and current-track metadata.").font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .padding()
            .accessibilityIdentifier("settings.view")
        }.navigationTitle("Juke Vibe Settings")
    }
}
