import SwiftUI

/// New Station: start with Records or Feelings; the other step is optional.
/// RadioScreen shows it for `JukeCoordinator.RadioRoute.newStation(draft)`;
/// the draft pre-fills the step, records and feelings.
///
/// Start creates the station (`POST radio/stations/ {seeds, feelings}`) and
/// asks the radio to play it after the current song.
struct NewStationScreen: View {
    @Environment(AppModel.self) private var model
    @State private var cache = CrateServicesCache()
    let draft: JukeCoordinator.NewStationDraft

    init(draft: JukeCoordinator.NewStationDraft) {
        self.draft = draft
    }

    var body: some View {
        NewStationContent(draft: draft, services: cache.services(api: model.api))
    }
}

private struct NewStationContent: View {
    let services: CrateServices
    @Environment(AppModel.self) private var model
    @Environment(JukeSettings.self) private var settings
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var flow: NewStationFlow
    @State private var browser: CrateBrowser
    @State private var isStarting = false
    @State private var startError: String?

    init(draft: JukeCoordinator.NewStationDraft, services: CrateServices) {
        self.services = services
        _flow = State(initialValue: NewStationFlow(draft: draft))
        _browser = State(initialValue: CrateBrowser(source: services.crate))
    }

    private var mode: CrateMode { CrateMode(settings.crateFlipDirection) }
    private var cardWidth: CGFloat { flow.step == .records ? mode.cardWidth : CrateMode.sideToSide.cardWidth }
    private var gentle: Animation? { reduceMotion ? nil : JukeMotion.easeOutSoft(0.48) }

    var body: some View {
        JukeCard(padding: EdgeInsets(top: 18, leading: 32, bottom: 20, trailing: 32)) {
            VStack(alignment: .leading, spacing: 12) {
                header
                ZStack(alignment: .top) {
                    if flow.step == .records {
                        recordsStep.transition(stepTransition)
                    } else {
                        feelingsStep.transition(stepTransition)
                    }
                }
                footer
            }
        }
        .frame(maxWidth: cardWidth)
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.55), value: cardWidth)
        .animation(gentle, value: flow.step)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .crateArtworkTint(flow.step == .records ? browser.focusedItem : nil, model: model)
        .task { await browser.loadIfNeeded() }
        .onExitCommand { model.coordinator.closeNewStation() }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("newStation.screen")
    }

    private var stepTransition: AnyTransition {
        reduceMotion ? .opacity : .opacity.combined(with: .offset(y: 10))
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 12) {
            Button {
                model.coordinator.closeNewStation()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 17, weight: .semibold))
                    .frame(width: JukeMetrics.minimumHitTarget, height: JukeMetrics.minimumHitTarget)
                    .background(theme.well.color, in: Circle())
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Back to Radio")
            .accessibilityIdentifier("newStation.back")
            VStack(alignment: .leading, spacing: 0) {
                Text("New station")
                    .font(JukeFont.display(24, weight: .bold))
                    .tracking(-0.5)
                    .accessibilityAddTraits(.isHeader)
                Text(flow.stepLine)
                    .font(JukeFont.body(14))
                    .foregroundStyle(theme.sub.color)
                    .contentTransition(.opacity)
            }
            Spacer(minLength: 8)
            HStack(spacing: 2) {
                Text("Start with").font(JukeFont.body(13)).foregroundStyle(theme.sub.color).padding(.trailing, 6)
                stepTab(.records, "Records")
                stepTab(.feelings, "Feelings")
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Start with")
        }
    }

    private func stepTab(_ step: NewStationFlow.Step, _ label: String) -> some View {
        let selected = flow.step == step
        return Button {
            withAnimation(gentle) { flow.select(step) }
        } label: {
            Text(label)
                .font(JukeFont.body(15, weight: .semibold))
                .foregroundStyle(selected ? theme.ink.color : theme.sub.color)
                .padding(.horizontal, 12)
                .frame(minHeight: JukeMetrics.minimumHitTarget)
                .overlay(alignment: .bottom) {
                    Rectangle().fill(selected ? theme.accent.color : .clear).frame(height: 2)
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("newStation.tab.\(label.lowercased())")
    }

    // MARK: Records

    private var focusedSeed: Radio.Seed? { browser.focusedItem?.seed }
    private var focusedIsPulled: Bool { focusedSeed.map(flow.isPulled) ?? false }

    private var recordsStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            CrateToolbar(browser: browser)
            CratePanel(
                browser: browser,
                pulledIDs: Set(flow.seeds.map(\.id)),
                onActivateFront: { item in withAnimation(gentle) { flow.togglePull(item.seed) } },
                activateLabel: { flow.pullActionName(for: $0.seed) }
            )
            HStack(spacing: 14) {
                Spacer(minLength: 0)
                CrateFocusCaption(item: browser.focusedItem)
                Button {
                    if let focusedSeed { withAnimation(gentle) { flow.togglePull(focusedSeed) } }
                } label: {
                    Text(flow.pullLabel(for: focusedSeed))
                        .font(JukeFont.body(14, weight: .semibold))
                        .padding(.horizontal, 14)
                        .frame(minHeight: 40)
                        .overlay(Capsule().strokeBorder(focusedIsPulled ? theme.accent.color : theme.line, lineWidth: 1.5))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .disabled(focusedSeed == nil)
                .accessibilityLabel(flow.pullAccessibilityLabel(for: focusedSeed))
                .accessibilityAddTraits(focusedIsPulled ? .isSelected : [])
                .accessibilityIdentifier("newStation.pull")
                Spacer(minLength: 0)
            }
            .frame(minHeight: 46)
            .animation(.easeOut(duration: 0.25), value: focusedIsPulled)
        }
    }

    // MARK: Feelings

    private var feelingsStep: some View {
        VStack(spacing: 14) {
            Text(flow.feelingsHeading)
                .font(JukeFont.display(28, weight: .bold))
                .tracking(-0.6)
                .multilineTextAlignment(.center)
            WrappingLayout(spacing: 8, alignment: .center) {
                ForEach(flow.feelingTokens, id: \.self) { feeling in
                    feelingToken(feeling)
                }
            }
            .frame(maxWidth: 640)
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Feelings")
            HStack(spacing: 8) {
                Text("Or in your words").font(JukeFont.body(13)).foregroundStyle(theme.sub.color)
                TextField("rainy train ride home", text: Bindable(flow).wordsDraft)
                    .textFieldStyle(.plain)
                    .font(JukeFont.body(15))
                    .padding(.horizontal, 14)
                    .frame(width: 260, height: JukeMetrics.minimumHitTarget)
                    .overlay(Capsule().strokeBorder(theme.line, lineWidth: 1))
                    .onSubmit { withAnimation(gentle) { _ = flow.addWords() } }
                    .onChange(of: flow.wordsDraft) { _, text in
                        let limited = NewStationFlow.limitedPhrase(text)
                        if limited != text { flow.wordsDraft = limited }
                    }
                    .accessibilityLabel("Or in your words")
                    .accessibilityIdentifier("newStation.words")
                Button("Add") { withAnimation(gentle) { _ = flow.addWords() } }
                    .buttonStyle(JukeWellButtonStyle())
                    .disabled(NewStationFlow.normalizedFeeling(flow.wordsDraft) == nil || flow.feelingsFull)
                    .accessibilityIdentifier("newStation.addWords")
            }
            previewTiles
            Text(flow.previewCaption)
                .font(JukeFont.body(13))
                .foregroundStyle(theme.sub.color)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    private func feelingToken(_ feeling: String) -> some View {
        let chosen = flow.isChosen(feeling)
        let emoji = NewStationFlow.isEmojiOnly(feeling)
        let name = NewStationFlow.feelingNames[feeling] ?? feeling
        return Button {
            withAnimation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.3)) { flow.toggleFeeling(feeling) }
        } label: {
            Text(emoji ? feeling : "“\(feeling)”")
                .font(emoji ? .system(size: 22) : JukeFont.body(14))
                .padding(.horizontal, emoji ? 0 : 14)
                .frame(minWidth: 48, minHeight: 48)
                .background(chosen ? theme.accentSoft.color : .clear, in: Capsule())
                .overlay(Capsule().strokeBorder(chosen ? theme.accent.color : theme.line, lineWidth: 1.5))
                .scaleEffect(chosen ? 1.06 : 1)
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(!chosen && flow.feelingsFull)
        .help(!chosen && flow.feelingsFull ? "Up to \(NewStationFlow.maxFeelings) feelings. Remove one to add another." : "")
        .accessibilityLabel(chosen ? "Remove \(name)" : "Feels \(name)")
        .accessibilityAddTraits(chosen ? .isSelected : [])
        .accessibilityIdentifier("newStation.feeling.\(feeling)")
    }

    private static let tileRotations: [Double] = [-6, 3, -2, 5, -4, 2, -3]

    private var previewTiles: some View {
        let records = flow.previewRecords(from: browser.items)
        return HStack(spacing: -12) {
            ForEach(Array(records.enumerated()), id: \.element.id) { index, seed in
                RecordArtwork(url: seed.artworkURL, seed: seed.spotifyId)
                    .frame(width: 72, height: 72)
                    .clipShape(RoundedRectangle(cornerRadius: JukeRadius.sleeve, style: .continuous))
                    .shadow(color: .black.opacity(0.2), radius: 8, y: 6)
                    .rotationEffect(.degrees(Self.tileRotations[index % Self.tileRotations.count]))
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
            }
        }
        .frame(height: 84)
        .padding(.top, 8)
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.5), value: records.map(\.id))
        .accessibilityHidden(true)
    }

    // MARK: Footer

    private var footer: some View {
        HStack(alignment: .center, spacing: 12) {
            WrappingLayout(spacing: 6, lineSpacing: 4, alignment: .leading) {
                Text("Your station:").font(JukeFont.body(14, weight: .bold)).frame(minHeight: 32)
                if flow.picks.isEmpty {
                    Text("nothing yet. Click a record twice, or choose Pull.")
                        .font(JukeFont.body(14))
                        .foregroundStyle(theme.sub.color)
                        .frame(minHeight: 32)
                }
                ForEach(flow.picks) { pick in
                    pickChip(pick).transition(.scale(scale: 0.85).combined(with: .opacity))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .animation(gentle, value: flow.picks)
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Your station")
            .accessibilityIdentifier("newStation.picks")

            Button {
                withAnimation(gentle) { flow.goToOtherStep() }
            } label: {
                Text(flow.otherStepLabel)
                    .font(JukeFont.body(14, weight: .semibold))
                    .underline()
                    .padding(.horizontal, 12)
                    .frame(minHeight: JukeMetrics.minimumHitTarget)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .fixedSize()
            .accessibilityIdentifier("newStation.otherStep")

            Button {
                Task { await start() }
            } label: {
                HStack(spacing: 8) {
                    if isStarting { ProgressView().controlSize(.small) } else { Image(systemName: "play.fill") }
                    Text(flow.startLabel).lineLimit(1)
                }
            }
            .buttonStyle(JukeAccentButtonStyle())
            .disabled(!flow.canStart || isStarting)
            .fixedSize()
            .accessibilityIdentifier("newStation.start")
        }
        .padding(.top, 12)
        .overlay(alignment: .top) { Rectangle().fill(theme.line).frame(height: 1) }
        .overlay(alignment: .bottomTrailing) {
            if let startError {
                Text(startError)
                    .font(JukeFont.body(12))
                    .foregroundStyle(theme.sub.color)
                    .offset(y: 18)
                    .accessibilityIdentifier("newStation.error")
            }
        }
    }

    private func pickChip(_ pick: NewStationPick) -> some View {
        HStack(spacing: 0) {
            Button {
                jump(to: pick)
            } label: {
                Text(pick.text)
                    .font(JukeFont.body(14))
                    .lineLimit(1)
                    .padding(.leading, 12)
                    .padding(.trailing, 4)
                    .frame(minHeight: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(pick.isRecord ? "Shows this record in the crate" : "Shows the feelings")
            Button {
                withAnimation(gentle) { flow.remove(pick) }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(theme.sub.color)
                    .frame(width: 32, height: 32)
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Remove \(pick.text)")
        }
        .background(theme.well.color, in: Capsule())
        .accessibilityElement(children: .contain)
    }

    private func jump(to pick: NewStationPick) {
        switch pick {
        case .record(let seed):
            withAnimation(gentle) { flow.select(.records) }
            Task { await browser.reveal(seed) }
        case .feeling:
            withAnimation(gentle) { flow.select(.feelings) }
        }
    }

    private func start() async {
        guard flow.canStart, !isStarting else { return }
        isStarting = true
        startError = nil
        defer { isStarting = false }
        let request = flow.createRequest
        do {
            try await StationStarter(creator: services.stations, coordinator: model.coordinator)
                .start(seeds: request.seeds, feelings: request.feelings)
        } catch is CancellationError {
        } catch {
            startError = error.localizedDescription
        }
    }
}

extension NewStationPick {
    var isRecord: Bool { if case .record = self { true } else { false } }
}

/// Wraps children onto lines, left-aligned or centred.
struct WrappingLayout: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8
    var alignment: HorizontalAlignment = .leading

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let lines = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = lines.map(\.width).max() ?? 0
        let height = lines.map(\.height).reduce(0, +) + lineSpacing * CGFloat(max(0, lines.count - 1))
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in arrange(width: bounds.width, subviews: subviews) {
            var x = alignment == .center ? bounds.minX + (bounds.width - line.width) / 2 : bounds.minX
            for index in line.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (line.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += line.height + lineSpacing
        }
    }

    private struct Line { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Line] {
        var lines: [Line] = []
        var current = Line()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width, !current.indices.isEmpty {
                lines.append(current)
                current = Line()
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { lines.append(current) }
        return lines
    }
}
