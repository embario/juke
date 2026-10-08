import SwiftUI

/// The single status line under the dial (reference: `statusAway`,
/// `statusPending`, `statusSuggest`, `statusLine`).
struct RadioStatusLine: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    let activity: DialActivity
    let source: RadioCardSource

    private var radio: RadioController { model.radio }

    var body: some View {
        HStack {
            content
        }
        .frame(maxWidth: .infinity, minHeight: 50)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.status")
    }

    @ViewBuilder
    private var content: some View {
        if radio.isPutAway {
            putAwayPane
        } else if let issue = radio.issue {
            RadioIssueView(issue: issue)
        } else if let name = activity.holdingName, let frequency = activity.holdingFrequency {
            line("Place \(name) anywhere on the dial · \(String(format: "%.1f", frequency)) FM")
        } else if activity.openingNewStation {
            line("Opening a fresh crate…")
        } else if let suggestion = radio.suggestion {
            suggestionPane(suggestion)
        } else if let pending = radio.pendingStation {
            Text("\(Text(pending.name).bold().foregroundStyle(theme.ink.color)) starts when this song ends, or press play on the dial.")
                .font(JukeFont.body(13))
                .foregroundStyle(theme.sub.color)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
        } else if radio.isPausedForEpisode, let notice = radio.notice {
            VStack(spacing: 6) {
                line(notice)
                Button("Resume station") { Task { await radio.togglePlayPause() } }
                    .buttonStyle(.link)
                    .accessibilityIdentifier("radio.resumeStation")
            }
        } else if let notice = radio.notice {
            line(notice)
        } else if source == .local {
            line("Playing in \(model.detection.providerName ?? "another app"). Press play on the dial to tune in to \(radio.tunedStation?.name ?? "My Station").")
        } else {
            line("Drag the dial to tune · Hold a station to move it · Spin the record to seek")
        }
    }

    private func line(_ text: String) -> some View {
        Text(text)
            .font(JukeFont.body(13))
            .foregroundStyle(theme.sub.color)
            .multilineTextAlignment(.center)
            .lineLimit(2)
            .frame(maxWidth: .infinity)
    }

    private var putAwayPane: some View {
        let position = radio.position(at: .now)
        let pending = radio.pendingStation
        let summary = radio.summary
        let emoji = (summary?.reactions ?? []).filter(RadioController.isEmoji).prefix(3).joined(separator: " ")
        let count = summary?.songCount ?? 0
        return HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text("Put away at \(RadioGesture.clock(position))" + (pending.map { " · \($0.name) is cued" } ?? ""))
                    .font(JukeFont.body(14, weight: .bold))
                Text("Today: \(count) \(count == 1 ? "song" : "songs")" + (emoji.isEmpty ? "" : " · \(emoji)") + ". Slide the record out to resume.")
                    .font(JukeFont.body(14))
                    .foregroundStyle(theme.sub.color)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button("Save as a memory") { Task { await radio.saveSessionAsMemory() } }
                .buttonStyle(PaneButtonStyle(fill: theme.card.color, text: theme.ink.color))
                .accessibilityIdentifier("radio.saveSession")
            Button(pending.map { "Play \($0.name)" } ?? "Play again") { Task { await radio.comeBack() } }
                .buttonStyle(PaneButtonStyle(fill: theme.accent.color, text: theme.onAccent.color))
                .accessibilityIdentifier("radio.playAgain")
        }
        .padding(EdgeInsets(top: 3, leading: 14, bottom: 3, trailing: 3))
        .background(theme.well.color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func suggestionPane(_ suggestion: Radio.StationSuggestion) -> some View {
        let matched = suggestion.matched.isEmpty ? radio.currentReactions.prefix(2).joined(separator: " ") : suggestion.matched.joined(separator: " ")
        return HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text("\(matched) fits \(suggestion.name)").font(JukeFont.body(14, weight: .bold))
                Text("Juke can tune there after this song.").font(JukeFont.body(14)).foregroundStyle(theme.sub.color)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button("Tune in next") { Task { await radio.acceptSuggestion() } }
                .buttonStyle(PaneButtonStyle(fill: theme.card.color, text: theme.ink.color))
            Button("Stay") { radio.dismissSuggestion() }
                .buttonStyle(PaneButtonStyle(fill: .clear, text: theme.ink.color))
        }
        .padding(EdgeInsets(top: 3, leading: 14, bottom: 3, trailing: 3))
        .background(theme.accentSoft.color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityIdentifier("radio.suggestion")
    }
}

/// A calm explanation of a radio problem with its next step.
struct RadioIssueView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    let issue: RadioIssue

    var body: some View {
        HStack(spacing: 8) {
            Text(issue.message)
                .font(JukeFont.body(14))
                .foregroundStyle(theme.ink.color)
                .frame(maxWidth: .infinity, alignment: .leading)
            switch issue {
            case .spotifyNotLinked:
                Button("Connect Spotify") { model.openSpotifyConnection() }
                    .buttonStyle(PaneButtonStyle(fill: theme.accent.color, text: theme.onAccent.color))
                    .accessibilityIdentifier("radio.connectSpotify")
            case .noActiveDevice, .spotifyFailed, .unavailable:
                Button("Try again") { Task { await retry() } }
                    .buttonStyle(PaneButtonStyle(fill: theme.card.color, text: theme.ink.color))
            case .noTracks, .signedOut:
                EmptyView()
            }
        }
        .padding(EdgeInsets(top: 3, leading: 14, bottom: 3, trailing: 3))
        .frame(minHeight: 50)
        .background(theme.well.color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.issue")
    }

    private func retry() async {
        let radio = model.radio
        if !radio.stationsLoaded { await radio.loadStations() }
        if radio.isOnAir { await radio.refresh() } else if !radio.hasTunedIn { await radio.tuneIn() } else { await radio.switchNow() }
    }
}

struct PaneButtonStyle: ButtonStyle {
    let fill: Color
    let text: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JukeFont.body(13, weight: .bold))
            .foregroundStyle(text)
            .lineLimit(1)
            .padding(.horizontal, 12)
            .frame(minHeight: JukeMetrics.minimumHitTarget)
            .background(fill, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// Station sheet: built from, feels like, keep out, keeps learning.
struct StationSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    let close: () -> Void
    @State private var keepOutDraft = ""

    private var radio: RadioController { model.radio }

    var body: some View {
        if let station = radio.currentStation {
            content(station)
        }
    }

    private func content(_ station: Radio.Station) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                HStack(spacing: 3) {
                    ForEach(Array(thumbnails(station).enumerated()), id: \.offset) { _, url in
                        RadioArtwork(url: url, cornerRadius: 5).frame(width: 30, height: 30)
                    }
                }
                VStack(alignment: .leading, spacing: 0) {
                    Text(station.name).font(JukeFont.display(22, weight: .bold)).tracking(-0.4)
                    Text("\(Text("\(station.frequencyLabel) FM").font(JukeFont.mono(13))) · \(station.isPersonal ? "Personal · learns as you listen" : "Your station")")
                        .font(JukeFont.body(13))
                        .foregroundStyle(theme.sub.color)
                }
                Spacer()
                Button("Done", action: close)
                    .buttonStyle(JukeWellButtonStyle())
                    .keyboardShortcut(.cancelAction)
                    .accessibilityIdentifier("radio.sheet.done")
            }

            VStack(alignment: .leading, spacing: 8) {
                RadioSheetLabel(text: "Built from")
                RadioFlowLayout(spacing: 6) {
                    ForEach(station.seeds) { seed in
                        Button { Task { await radio.removeSeed(seed, from: station.id) } } label: {
                            HStack(spacing: 8) {
                                RadioArtwork(url: seed.artworkURL, cornerRadius: 15).frame(width: 30, height: 30).clipShape(Circle())
                                Text(seed.title).font(JukeFont.body(13)).lineLimit(1)
                                Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                            }
                            .padding(.leading, 4)
                            .padding(.trailing, 12)
                            .frame(minHeight: 40)
                            .overlay(Capsule().strokeBorder(theme.line, lineWidth: 1))
                            .contentShape(Capsule())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Remove \(seed.title) from this station")
                    }
                    Button {
                        close()
                        model.coordinator.openNewStation(.init(start: .records, seeds: station.seeds, feelings: station.feelings))
                    } label: {
                        Text("Pull more records")
                            .font(JukeFont.body(13, weight: .semibold))
                            .padding(.horizontal, 14)
                            .frame(minHeight: 40)
                            .overlay(Capsule().strokeBorder(theme.line, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])))
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("radio.sheet.pullMore")
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                RadioSheetLabel(text: "Feels like")
                let songFeelings = radio.currentReactions.filter { !station.feelings.contains($0) }
                if station.feelings.isEmpty, songFeelings.isEmpty {
                    Text("React to songs with emoji or words and this station leans into them.")
                        .font(JukeFont.body(13)).foregroundStyle(theme.sub.color)
                }
                RadioFlowLayout(spacing: 6) {
                    ForEach(station.feelings, id: \.self) { feeling in
                        feelingChip(feeling) { Task { await radio.removeFeeling(feeling, from: station.id) } }
                    }
                    ForEach(songFeelings, id: \.self) { feeling in
                        feelingChip(feeling) { Task { await radio.toggleReaction(feeling) } }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                RadioSheetLabel(text: "Keep out")
                if !station.exclusions.isEmpty {
                    RadioFlowLayout(spacing: 6) {
                        ForEach(station.exclusions) { exclusion in
                            Button { Task { await radio.restoreExclusion(exclusion, on: station.id) } } label: {
                                HStack(spacing: 6) {
                                    Text(exclusion.label.isEmpty ? exclusion.value : exclusion.label).strikethrough()
                                    Text(exclusionKind(exclusion)).font(JukeFont.body(11)).foregroundStyle(theme.sub.color)
                                }
                                .font(JukeFont.body(13))
                                .padding(.horizontal, 12)
                                .frame(minHeight: 36)
                                .background(theme.well.color, in: Capsule())
                                .overlay(Capsule().strokeBorder(theme.line, lineWidth: 1))
                                .contentShape(Capsule())
                            }
                            .buttonStyle(.plain)
                            .help("Let it back in")
                            .accessibilityLabel("Let \(exclusion.label.isEmpty ? exclusion.value : exclusion.label) back in")
                        }
                    }
                }
                HStack(spacing: 6) {
                    TextField("Keep out an artist, song or genre", text: $keepOutDraft)
                        .textFieldStyle(.plain)
                        .font(JukeFont.body(14))
                        .padding(.horizontal, 12)
                        .frame(height: 40)
                        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(theme.line, lineWidth: 1))
                        .onSubmit { addKeepOut(station.id) }
                        .accessibilityLabel("Keep out an artist, song or genre")
                    Button("Keep out") { addKeepOut(station.id) }
                        .buttonStyle(PaneButtonStyle(fill: theme.well.color, text: theme.ink.color))
                        .disabled(keepOutDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }

            Spacer(minLength: 0)
            Divider().overlay(theme.line)
            HStack(spacing: 12) {
                Text("Tip: press and hold a station on the dial to move it to a new frequency.")
                    .font(JukeFont.body(13))
                    .foregroundStyle(theme.sub.color)
                Spacer()
                Toggle("Keeps learning", isOn: Binding(
                    get: { station.learning },
                    set: { value in Task { await radio.setLearning(value, for: station.id) } }
                ))
                .toggleStyle(.switch)
                .tint(theme.accent.color)
                .font(JukeFont.body(13, weight: .semibold))
                .accessibilityIdentifier("radio.sheet.learning")
            }
        }
        .padding(EdgeInsets(top: 22, leading: 28, bottom: 22, trailing: 28))
        .foregroundStyle(theme.ink.color)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.stationSheet")
    }

    private func thumbnails(_ station: Radio.Station) -> [URL?] {
        let urls = station.thumbnailURLs
        if !urls.isEmpty { return urls.prefix(3).map { Optional($0) } }
        return station.seeds.prefix(3).map(\.artworkURL)
    }

    private func feelingChip(_ feeling: String, remove: @escaping () -> Void) -> some View {
        Button(action: remove) {
            HStack(spacing: 6) {
                Text(RadioController.isEmoji(feeling) ? feeling : "“\(feeling)”")
                Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
            }
            .font(JukeFont.body(14))
            .padding(.horizontal, 12)
            .frame(minHeight: 36)
            .background(theme.accentSoft.color, in: Capsule())
            .overlay(Capsule().strokeBorder(theme.accent.color, lineWidth: 1.5))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Remove \(feeling)")
    }

    private func exclusionKind(_ exclusion: Radio.Exclusion) -> String {
        let kind: String = switch exclusion.kind {
        case .track: "song"
        case .artist: "artist"
        case .genre: "genre"
        case .text, .unknown: "kept out"
        }
        return exclusion.scope == .everywhere ? "\(kind) · everywhere" : kind
    }

    private func addKeepOut(_ stationID: Radio.ID) {
        let text = keepOutDraft
        keepOutDraft = ""
        Task { await radio.addExclusion(text, to: stationID) }
    }
}

/// Lyrics: "coming soon" until a licensed provider is chosen.
struct LyricsSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    let source: RadioCardSource
    let close: () -> Void

    var body: some View {
        let isRadio = source != .local
        let title = isRadio ? model.radio.track?.title ?? "" : model.detection.track?.title ?? ""
        let artist = isRadio ? model.radio.track?.artist ?? "" : model.detection.track?.artist ?? ""
        let artwork = isRadio ? model.radio.track?.artworkURL : model.detection.track?.artworkURL
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                RadioArtwork(url: artwork).frame(width: 44, height: 44)
                VStack(alignment: .leading, spacing: 0) {
                    Text(title).font(JukeFont.body(16, weight: .bold)).lineLimit(1)
                    Text(artist).font(JukeFont.body(13)).foregroundStyle(theme.sub.color).lineLimit(1)
                }
                Spacer()
                Button("Back to the record", action: close)
                    .buttonStyle(JukeWellButtonStyle())
                    .keyboardShortcut(.cancelAction)
            }
            Spacer()
            VStack(spacing: 10) {
                Image(systemName: "text.quote").font(.system(size: 30, weight: .medium)).foregroundStyle(theme.sub.color)
                Text("Lyrics are coming soon").font(JukeFont.display(22, weight: .bold))
                Text("Juke will show lyrics line by line, following the song, once a licensed lyrics provider is in place.")
                    .font(JukeFont.body(15))
                    .foregroundStyle(theme.sub.color)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 420)
            }
            .frame(maxWidth: .infinity)
            Spacer()
        }
        .padding(EdgeInsets(top: 22, leading: 28, bottom: 22, trailing: 28))
        .foregroundStyle(theme.ink.color)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("radio.lyrics")
    }
}

/// Wraps chips onto as many lines as needed.
struct RadioFlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(subviews, width: proposal.width ?? .infinity)
        let width = rows.map(\.width).max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = rows[rows.count - 1].indices.isEmpty ? size.width : rows[rows.count - 1].width + spacing + size.width
            if needed > width, !rows[rows.count - 1].indices.isEmpty {
                rows.append(Row())
            }
            var row = rows[rows.count - 1]
            row.width = row.indices.isEmpty ? size.width : row.width + spacing + size.width
            row.height = max(row.height, size.height)
            row.indices.append(index)
            rows[rows.count - 1] = row
        }
        return rows.filter { !$0.indices.isEmpty }
    }
}
