import SwiftUI

/// What the record-in-its-sleeve sheet offers, and when it appears. Kept apart from the view so it can be tested.
enum SleeveActions {
    enum Action: String, CaseIterable, Identifiable {
        case newStation, browseAlbum, favorite, saveForLater
        var id: String { rawValue }
    }

    struct Item: Identifiable, Equatable {
        let action: Action
        let title: String
        let systemImage: String
        let isEnabled: Bool
        /// Why an action is unavailable (shown under it).
        let note: String?
        var id: Action { action }
    }

    /// The four actions for the song that was playing. Favorites and Save for later have no store to
    /// write to yet, so they are listed, disabled, with a short note.
    static func items(for track: Radio.Track?) -> [Item] {
        let hasSong = track != nil
        let canBrowse = track.flatMap(DetailRoute.album(of:)) != nil
        return [
            Item(action: .newStation, title: "Start a new station from this song", systemImage: "dot.radiowaves.left.and.right",
                 isEnabled: hasSong, note: hasSong ? nil : "Nothing was playing."),
            Item(action: .browseAlbum, title: "Browse the album", systemImage: "square.stack",
                 isEnabled: canBrowse, note: canBrowse ? nil : "This song doesn’t say which album it is on."),
            Item(action: .favorite, title: "Save to favorites", systemImage: "heart",
                 isEnabled: false, note: "Coming soon."),
            Item(action: .saveForLater, title: "Save for later", systemImage: "clock.badge.checkmark",
                 isEnabled: false, note: "Coming soon."),
        ]
    }

    /// The sheet opens when the record goes into its sleeve, and only then: not when a record that was
    /// already put away is shown again, and not when it comes back out.
    static func shouldPresent(wasPutAway: Bool, isPutAway: Bool) -> Bool { !wasPutAway && isPutAway }

    /// The album the "Browse the album" action opens.
    static func albumRoute(for track: Radio.Track?) -> DetailRoute? { track.flatMap(DetailRoute.album(of:)) }
}

/// The sheet shown when the record slides into its sleeve (playback is already paused by then).
/// Dismissing it leaves playback paused with the record in the sleeve; "Play again" is on the page behind it
/// and in the sheet.
struct SleeveActionsSheet: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let track: Radio.Track?
    let onBrowse: (DetailRoute) -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                VStack(spacing: 2) {
                    Text("Paused").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text(track?.title ?? "Record put away").font(.headline).multilineTextAlignment(.center).lineLimit(2)
                    if let artist = track?.artist { Text(artist).font(.subheadline).foregroundStyle(.secondary).lineLimit(1) }
                }
                .padding(.top, 20)
                .accessibilityElement(children: .combine)
                VStack(spacing: 10) {
                    ForEach(SleeveActions.items(for: track)) { item in
                        VStack(spacing: 2) {
                            Button { perform(item.action) } label: {
                                Label(item.title, systemImage: item.systemImage).frame(maxWidth: .infinity, minHeight: 28)
                            }
                            .buttonStyle(.bordered).controlSize(.large)
                            .disabled(!item.isEnabled)
                            .accessibilityIdentifier("sleeve.\(item.action.rawValue)")
                            if let note = item.note, !item.isEnabled {
                                Text(note).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                Button { dismiss(); Task { await model.radio.comeBack() } } label: {
                    Label("Play again", systemImage: "play.fill").frame(maxWidth: .infinity, minHeight: 28)
                }
                .buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
                .accessibilityIdentifier("sleeve.playAgain")
                Button("Keep it paused") { dismiss() }
                    .accessibilityIdentifier("sleeve.keepPaused")
            }
            .padding(.horizontal, 20).padding(.bottom, 16)
        }
        .presentationDetents([.medium, .large])
        .accessibilityIdentifier("sleeve.sheet")
    }

    private func perform(_ action: SleeveActions.Action) {
        switch action {
        case .newStation:
            dismiss()
            Task { await model.radio.startRadioFromCurrentTrack() }
        case .browseAlbum:
            if let route = SleeveActions.albumRoute(for: track) { onBrowse(route) }
        case .favorite, .saveForLater:
            break
        }
    }
}
