import SwiftUI

/// What a station is made of: its records and feelings, what it keeps out, and
/// whether it learns from reactions.
struct StationSheet: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let stationID: Radio.ID
    @State private var keepOut = ""

    var body: some View {
        let radio = model.radio
        NavigationStack {
            if let station = radio.station(stationID) {
                Form {
                    Section("Records") {
                        if station.seeds.isEmpty { Text("No records yet.").foregroundStyle(.secondary) }
                        ForEach(station.seeds) { seed in
                            HStack {
                                VStack(alignment: .leading) { Text(seed.title); if let subtitle = seed.subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary) } }
                                Spacer()
                                Button { Task { await radio.removeSeed(seed, from: station.id) } } label: { Image(systemName: "minus.circle") }.buttonStyle(.plain)
                                    .accessibilityLabel("Remove \(seed.title)")
                            }
                        }
                        Button("Pull more records", systemImage: "plus") {
                            model.coordinator.openNewStation(.init(start: .records, seeds: station.seeds, feelings: station.feelings))
                            dismiss()
                        }
                    }
                    Section("Feelings") {
                        if station.feelings.isEmpty { Text("None yet. React to songs and they appear here.").foregroundStyle(.secondary) }
                        ForEach(station.feelings, id: \.self) { feeling in
                            HStack { Text(feeling); Spacer()
                                Button { Task { await radio.removeFeeling(feeling, from: station.id) } } label: { Image(systemName: "minus.circle") }.buttonStyle(.plain)
                                    .accessibilityLabel("Remove \(feeling)")
                            }
                        }
                    }
                    Section("Keeping out") {
                        ForEach(station.exclusions) { exclusion in
                            HStack { Text(exclusion.label.isEmpty ? exclusion.value : exclusion.label); Spacer()
                                Button("Let back in") { Task { await radio.restoreExclusion(exclusion, on: station.id) } }.font(.caption)
                            }
                        }
                        HStack {
                            TextField("Keep out an artist, genre or mood", text: $keepOut).onSubmit(add)
                            Button("Add", action: add).disabled(keepOut.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                    }
                    Section {
                        Toggle("Learn from my reactions", isOn: Binding(get: { station.learning }, set: { value in Task { await radio.setLearning(value, for: station.id) } }))
                    } footer: { Text("When on, songs you love and the feelings you add shape this station.") }
                }
                .navigationTitle(station.name).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            } else {
                ContentUnavailableView("Station not found", systemImage: "dot.radiowaves.left.and.right")
            }
        }
    }

    private func add() {
        let text = keepOut; keepOut = ""
        Task { await model.radio.addExclusion(text, to: stationID) }
    }
}

/// Shown while the record is slid back into its sleeve.
struct PutAwayCard: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        let radio = model.radio
        VStack(spacing: 14) {
            Image(systemName: "tray.and.arrow.down.fill").font(.system(size: 44)).foregroundStyle(model.atmosphere.primary)
            Text("Record put away").font(.title2.bold())
            if let summary = radio.summary, summary.songCount > 0 {
                Text("\(summary.songCount) \(summary.songCount == 1 ? "song" : "songs") this session")
                    .foregroundStyle(.secondary)
                if !summary.reactions.isEmpty { Text(summary.reactions.prefix(6).joined(separator: " ")).font(.title3) }
                Button("Save as a memory", systemImage: "bookmark") { Task { await radio.saveSessionAsMemory() } }.buttonStyle(.bordered)
            }
            Button { Task { await radio.comeBack() } } label: { Label(playLabel, systemImage: "play.fill").frame(maxWidth: 240) }
                .buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
        }
        .padding(20).frame(maxWidth: .infinity)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
    }

    private var playLabel: String {
        if let pending = model.radio.pendingStation { return "Play \(pending.name)" }
        return "Play again"
    }
}
