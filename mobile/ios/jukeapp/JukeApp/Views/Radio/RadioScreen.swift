import SwiftUI

/// Radio on iPhone: one card with the sleeve, transport, reactions and the
/// station strip. Touch gestures (vinyl, FM dial) come in later slices.
struct RadioScreen: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        let radio = model.radio
        Group {
            if case .newStation(let draft) = model.coordinator.radioRoute {
                NewStationScreen(draft: draft)
            } else if !radio.hasTunedIn {
                FirstRunCard()
            } else {
                NowPlayingCard()
            }
        }
        .navigationTitle(model.coordinator.radioRoute == .nowPlaying ? "Radio" : "New station")
        .navigationBarTitleDisplayMode(.inline)
        .background(VibeBackground(atmosphere: model.atmosphere))
    }
}

private struct FirstRunCard: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: "dot.radiowaves.left.and.right").font(.system(size: 54)).foregroundStyle(model.atmosphere.primary)
            Text("Your station is ready").font(.title.bold())
            Text("Juke picks songs from your taste and plays them on Spotify, one after another.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            IssueView()
            Button { Task { await model.radio.tuneIn() } } label: {
                Label("Tune in", systemImage: "play.fill").frame(maxWidth: 260)
            }
            .buttonStyle(.borderedProminent).controlSize(.large).tint(model.atmosphere.primary)
            .disabled(model.radio.isBusy)
            Spacer()
        }.padding(24)
    }
}

private struct NowPlayingCard: View {
    @Environment(VibeAppModel.self) private var model
    @State private var visibleHeight: CGFloat = 900

    var body: some View {
        let radio = model.radio
        ScrollView {
            VStack(spacing: 14) {
                StationHeader()
                if radio.isPutAway { PutAwayCard() }
                SleeveAndRecord(track: radio.track, side: RadioLayout.sleeveSide(visibleHeight: visibleHeight))
                VStack(spacing: 4) {
                    Text(radio.track?.title ?? "Nothing playing").font(.title2.bold()).multilineTextAlignment(.center).lineLimit(2)
                    Text(radio.track?.artist ?? "Press play to start your station").foregroundStyle(.secondary).lineLimit(1)
                    if let album = radio.track?.album { Text(album).font(.caption).foregroundStyle(.tertiary).lineLimit(1) }
                }
                ProgressScrubber()
                Transport()
                ReactionStrip()
                IssueView()
                if let notice = radio.notice { Text(notice).font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center) }
                if radio.isPausedForEpisode {
                    Button("Resume station") { Task { await radio.togglePlayPause() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("radio.resumeStation")
                }
                FMDialView()
            }
            .padding(.horizontal, 20).padding(.vertical, 12)
        }
        .onScrollGeometryChange(for: CGFloat.self) { $0.containerSize.height - $0.contentInsets.top - $0.contentInsets.bottom } action: { _, height in visibleHeight = height }
        .refreshable { await radio.refresh() }
    }
}

private struct StationHeader: View {
    @Environment(VibeAppModel.self) private var model
    @State private var showingStation = false

    var body: some View {
        let station = model.radio.currentStation
        HStack {
            Button { showingStation = station != nil } label: {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) { Text(station?.name ?? "Radio").font(.headline); if station != nil { Image(systemName: "chevron.right").font(.caption2) } }
                    if let station { Text("FM \(station.frequencyLabel)").font(.caption.monospaced()).foregroundStyle(.secondary) }
                }.foregroundStyle(.primary)
            }.buttonStyle(.plain).accessibilityHint("Shows what this station is made of")
            Spacer()
            if let pending = model.radio.pendingStation, pending.id != station?.id {
                Button("Switch to \(pending.name)") { Task { await model.radio.switchNow() } }
                    .buttonStyle(.bordered).controlSize(.small)
            }
        }
        .sheet(isPresented: $showingStation) { if let id = station?.id { StationSheet(stationID: id) } }
    }
}

/// The sleeve with the record sliding out behind it. Long-press the sleeve for
/// "start radio from this song" and links into the Library.
struct SleeveAndRecord: View {
    @Environment(VibeAppModel.self) private var model
    let track: Radio.Track?
    var side: CGFloat = RadioLayout.maxSleeve
    /// How far the record slides out; its label must stay mostly clear of the sleeve to be grabbable.
    private var discOffset: CGFloat { RadioLayout.discOffset(side: side) }

    var body: some View {
        ZStack(alignment: .leading) {
            VinylDisc(track: track, size: side, outOffset: discOffset)
            AsyncImage(url: track?.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { Color(.secondarySystemBackground); Image(systemName: "music.note").font(.system(size: 44)).foregroundStyle(.secondary) }
            }
            .frame(width: side, height: side)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .shadow(color: .black.opacity(0.3), radius: 16, y: 8)
            .contextMenu {
                if let track {
                    Button("Start radio from this song", systemImage: "dot.radiowaves.left.and.right") { Task { await model.radio.startRadioFromCurrentTrack() } }
                    if let albumID = track.albumId {
                        Button("Open the album", systemImage: "square.stack") { open(.album, albumID, track.album ?? track.title) }
                    }
                    if let artistID = track.artistId {
                        Button("Open the artist", systemImage: "person") { open(.artist, artistID, track.artist) }
                    }
                }
            }
            .accessibilityLabel(track.map { "\($0.title) by \($0.artist)" } ?? "No song playing")
        }
        .frame(width: side + discOffset, height: side, alignment: .leading)
        .frame(maxWidth: .infinity)
    }

    private func open(_ kind: Radio.SeedKind, _ id: String, _ title: String) {
        model.coordinator.focusInLibrary(.init(kind: kind, spotifyId: id, title: title))
        model.tab = .library
    }
}

private struct ProgressScrubber: View {
    @Environment(VibeAppModel.self) private var model
    @State private var scrubbing: Double?

    var body: some View {
        let radio = model.radio
        TimelineView(.periodic(from: .now, by: 0.5)) { context in
            let duration = max(radio.duration, 1)
            let position = scrubbing ?? radio.position(at: context.date)
            VStack(spacing: 4) {
                Slider(value: Binding(get: { min(position, duration) }, set: { scrubbing = $0 }), in: 0...duration) { editing in
                    if !editing, let target = scrubbing { scrubbing = nil; Task { await radio.seek(to: target) } }
                }
                .disabled(radio.track == nil)
                HStack {
                    Text(Self.format(position)); Spacer(); Text(Self.format(radio.duration))
                }.font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
    }

    static func format(_ seconds: TimeInterval) -> String {
        let total = Int(max(0, seconds)); return String(format: "%d:%02d", total / 60, total % 60)
    }
}

private struct Transport: View {
    @Environment(VibeAppModel.self) private var model
    @State private var lyricsSoon = false

    var body: some View {
        let radio = model.radio
        HStack(spacing: 36) {
            Menu {
                Button("Save this moment", systemImage: "bookmark") { Task { await radio.saveMoment() } }
                Button("Put the record away", systemImage: "tray.and.arrow.down") { Task { await radio.putAway() } }
                Button("Lyrics", systemImage: "text.quote") { lyricsSoon = true }
            } label: { Image(systemName: "ellipsis.circle").font(.title2) }
            Button { Task { await radio.togglePlayPause() } } label: {
                Image(systemName: radio.isPlaying ? "pause.circle.fill" : "play.circle.fill").font(.system(size: 64))
            }
            .accessibilityLabel(radio.isPlaying ? "Pause" : "Play")
            Button { Task { await radio.skip() } } label: { Image(systemName: "forward.fill").font(.title2) }
                .accessibilityLabel("Next song")
                .contextMenu {
                    Button("Not on this station", systemImage: "minus.circle") { Task { await radio.keepOut(.notOnStation) } }
                    Button("Less of this artist", systemImage: "person.crop.circle.badge.minus") { Task { await radio.keepOut(.lessArtist) } }
                    Button("Never this artist", systemImage: "nosign") { Task { await radio.keepOut(.neverArtist) } }
                }
        }
        .foregroundStyle(model.atmosphere.primary)
        .disabled(radio.isBusy)
        .alert("Lyrics are coming soon", isPresented: $lyricsSoon) { Button("OK", role: .cancel) {} } message: { Text("Juke will show lyrics once a licensed provider is chosen.") }
    }
}

private struct ReactionStrip: View {
    @Environment(VibeAppModel.self) private var model
    @State private var words = ""
    @State private var addingWords = false

    var body: some View {
        let radio = model.radio
        VStack(spacing: 10) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(radio.stripReactions, id: \.self) { reaction in
                        let selected = radio.currentReactions.contains(reaction)
                        Button { Task { await radio.toggleReaction(reaction) } } label: {
                            Text(reaction).font(.title3).padding(.horizontal, 12).padding(.vertical, 8)
                                .background(selected ? model.atmosphere.primary.opacity(0.3) : Color.secondary.opacity(0.12), in: Capsule())
                        }.buttonStyle(.plain)
                    }
                    Button { addingWords = true } label: { Image(systemName: "plus").padding(10).background(Color.secondary.opacity(0.12), in: Circle()) }
                        .buttonStyle(.plain).accessibilityLabel("Add your own reaction")
                }
            }.disabled(radio.track == nil)
            if let suggestion = radio.suggestion {
                HStack {
                    Text("Sounds like \(suggestion.name)").font(.footnote)
                    Button("Tune") { Task { await radio.acceptSuggestion() } }.buttonStyle(.bordered).controlSize(.small)
                    Button("Not now") { radio.dismissSuggestion() }.controlSize(.small)
                }
            }
        }
        .alert("How does it feel?", isPresented: $addingWords) {
            TextField("A few words", text: $words)
            Button("Add") { let text = words; words = ""; Task { await radio.addWords(text) } }
            Button("Cancel", role: .cancel) { words = "" }
        }
    }
}

/// A calm explanation and next step for whatever stopped the radio.
struct IssueView: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.openURL) private var openURL

    var body: some View {
        if let issue = model.radio.issue {
            VStack(spacing: 8) {
                Text(issue.message).font(.callout).multilineTextAlignment(.center)
                switch issue {
                case .noActiveDevice:
                    Button("Open Spotify") { if let url = URL(string: "spotify://") { openURL(url) } }.buttonStyle(.bordered)
                case .spotifyNotLinked:
                    Button("Connect Spotify") { openURL(AppConfiguration.currentFrontendURL) }.buttonStyle(.bordered)
                default: EmptyView()
                }
            }
            .padding(14).frame(maxWidth: .infinity)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
        }
    }
}

/// Compact player shown above the tab bar on every tab except Radio.
struct MiniPlayerPill: View {
    @Environment(VibeAppModel.self) private var model

    var body: some View {
        let radio = model.radio
        if radio.isOnAir, let track = radio.track {
            HStack(spacing: 11) {
                AsyncImage(url: track.artworkURL) { $0.resizable().scaledToFill() } placeholder: { Color.secondary.opacity(0.15) }
                    .frame(width: 42, height: 42).clipShape(RoundedRectangle(cornerRadius: 8))
                VStack(alignment: .leading, spacing: 2) {
                    Text(track.title).font(.subheadline.bold()).lineLimit(1)
                    Text(track.artist).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Button { Task { await radio.togglePlayPause() } } label: { Image(systemName: radio.isPlaying ? "pause.fill" : "play.fill").font(.title3) }
                Button { Task { await radio.skip() } } label: { Image(systemName: "forward.fill").font(.title3) }
            }
            .padding(10).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18)).padding(.horizontal).padding(.bottom, 4)
            .contentShape(Rectangle()).onTapGesture { model.tab = .radio }
        } else {
            NowPlayingPill()
        }
    }
}
