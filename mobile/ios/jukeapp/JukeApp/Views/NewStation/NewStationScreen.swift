import SwiftUI

/// New Station on iPhone, as a short wizard: how to begin (feelings or records),
/// the chosen step, the other step (optional), then a name and a few words about
/// the station. Mirrors the Mac flow (`NewStationFlow` is shared).
///
/// "Create" posts `radio/stations/` with the picks and tunes to the new station.
struct NewStationScreen: View {
    @Environment(VibeAppModel.self) private var model
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var flow: NewStationFlow
    @State private var page: NewStationPage
    private let startedWithPicks: Bool
    @State private var forward = true
    @State private var name = ""
    @State private var details = ""
    @State private var query = ""
    @State private var kind: Radio.SeedKind = .track
    @State private var results: [Radio.CrateItem] = []
    @State private var searching = false
    @State private var saving = false
    @State private var error: String?

    init(draft: JukeCoordinator.NewStationDraft) {
        let initialFlow = NewStationFlow(draft: draft)
        _flow = State(initialValue: initialFlow)
        startedWithPicks = NewStationWizard.initialPage(for: draft) == .first
        var start = NewStationWizard.initialPage(for: draft)
        #if DEBUG
        if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--uitesting-wizard-page=") })?.dropFirst(24),
           let raw = Int(value), let forced = NewStationPage(rawValue: raw) {
            start = forced
            if forced == .finish, !initialFlow.canStart { initialFlow.toggleFeeling("🌙"); initialFlow.toggleFeeling("☕") }
        }
        #endif
        _page = State(initialValue: start)
    }

    private var gentle: Animation? { reduceMotion ? nil : .smooth(duration: 0.45) }

    var body: some View {
        VStack(spacing: 0) {
            header
            ZStack {
                content
                    .id(page)
                    .transition(reduceMotion ? .opacity : .asymmetric(
                        insertion: .move(edge: forward ? .trailing : .leading).combined(with: .opacity),
                        removal: .move(edge: forward ? .leading : .trailing).combined(with: .opacity)))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipped()
            footer
        }
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { model.coordinator.closeNewStation() } } }
        .onChange(of: model.coordinator.radioRoute) { _, route in
            // A new draft pushed while this screen is showing (for example "Pull more records").
            if case .newStation(let next) = route {
                flow = NewStationFlow(draft: next)
                go(to: NewStationWizard.initialPage(for: next), forward: true)
            }
        }
        .accessibilityIdentifier("newStation.screen")
    }

    // MARK: Chrome

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                ForEach(NewStationPage.allCases, id: \.self) { dot in
                    Capsule().fill(dot <= page ? theme.accent.color : theme.line)
                        .frame(width: dot == page ? 26 : 8, height: 8)
                }
            }
            .accessibilityElement().accessibilityLabel("Step \(page.rawValue + 1) of \(NewStationPage.allCases.count)")
            Text(title).font(.title.bold()).foregroundStyle(theme.ink.color)
            Text(subtitle).font(.subheadline).foregroundStyle(theme.sub.color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 12)
    }

    private var title: String {
        switch page {
        case .start: "New station"
        case .first, .second:
            page.step(path: flow.path) == .records ? "Pull some records" : flow.feelingsHeading
        case .finish: "Name your station"
        }
    }

    private var subtitle: String {
        switch page {
        case .start: "How do you want to begin?"
        case .first, .second: flow.stepLine
        case .finish: "Optional, but it makes it yours."
        }
    }

    private var footer: some View {
        VStack(spacing: 10) {
            if let error { Label(error, systemImage: "exclamationmark.triangle.fill").font(.footnote).foregroundStyle(theme.ink.color) }
            switch page {
            case .start:
                EmptyView()
            case .finish:
                Button { Task { await create(.afterCurrentSong) } } label: { Text(flow.startLabel).frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large).disabled(!flow.canStart || saving)
                    .accessibilityIdentifier("newStation.start")
                Button("Play it now") { Task { await create(.now) } }.disabled(!flow.canStart || saving)
            default:
                Button { advance() } label: { Text(NewStationWizard.advanceLabel(from: page, flow: flow)).frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!NewStationWizard.canAdvance(from: page, flow: flow))
                    .accessibilityIdentifier("newStation.next")
            }
            if page != .start {
                Button("Back") { back() }.font(.subheadline).accessibilityIdentifier("newStation.back")
            }
        }
        .padding(.horizontal, 20).padding(.vertical, 12)
        .background(.bar)
    }

    // MARK: Pages

    @ViewBuilder private var content: some View {
        switch page {
        case .start: startPage
        case .first, .second:
            if page.step(path: flow.path) == .records { recordsPage } else { feelingsPage }
        case .finish: finishPage
        }
    }

    private var startPage: some View {
        VStack(spacing: 14) {
            choiceCard("Feelings", "Pick emoji or a few words and Juke finds records that feel that way.", symbol: "face.smiling", step: .feelings)
            choiceCard("Records", "Start from songs, artists or albums you love.", symbol: "opticaldisc", step: .records)
            Spacer()
        }
        .padding(.horizontal, 20)
    }

    private func choiceCard(_ title: String, _ detail: String, symbol: String, step: NewStationFlow.Step) -> some View {
        Button {
            flow.select(step)
            go(to: .first, forward: true)
            if step == .records { Task { await search() } }
        } label: {
            HStack(spacing: 16) {
                Image(systemName: symbol).font(.title).frame(width: 44).foregroundStyle(theme.accent.color)
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.headline).foregroundStyle(theme.ink.color)
                    Text(detail).font(.subheadline).foregroundStyle(theme.sub.color).multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").foregroundStyle(theme.sub.color)
            }
            .padding(18)
            .background(theme.card.color, in: RoundedRectangle(cornerRadius: JukeRadius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("newStation.choose.\(title.lowercased())")
    }

    private var recordsPage: some View {
        VStack(spacing: 10) {
            Picker("Type", selection: $kind) {
                Text("Songs").tag(Radio.SeedKind.track); Text("Artists").tag(Radio.SeedKind.artist); Text("Albums").tag(Radio.SeedKind.album)
            }
            .pickerStyle(.segmented).padding(.horizontal, 20)
            TextField("Search for a song, artist or album", text: $query)
                .textFieldStyle(.roundedBorder).submitLabel(.search).padding(.horizontal, 20)
                .onSubmit { Task { await search() } }
            if !flow.seeds.isEmpty { pickedRow(records: true) }
            List {
                if searching { ProgressView().frame(maxWidth: .infinity).listRowBackground(Color.clear) }
                ForEach(results) { item in
                    Button { flow.togglePull(item.seed) } label: { resultRow(item) }.listRowBackground(Color.clear)
                }
            }
            .listStyle(.plain).scrollContentBackground(.hidden).scrollDismissesKeyboard(.interactively)
        }
        .task(id: kind) { await search() }
    }

    private func resultRow(_ item: Radio.CrateItem) -> some View {
        let pulled = flow.isPulled(item.seed)
        return HStack(spacing: 12) {
            AsyncImage(url: item.artworkURL) { $0.resizable().scaledToFill() } placeholder: {
                ZStack { theme.well.color; Image(systemName: item.kind == .artist ? "person.fill" : "music.note").foregroundStyle(theme.sub.color) }
            }
            .frame(width: 48, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: item.kind == .artist ? 24 : 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.body.weight(.semibold)).foregroundStyle(theme.ink.color).lineLimit(1)
                if let subtitle = item.subtitle { Text(subtitle).font(.caption).foregroundStyle(theme.sub.color).lineLimit(1) }
            }
            Spacer(minLength: 0)
            Image(systemName: pulled ? "checkmark.circle.fill" : "plus.circle").font(.title3)
                .foregroundStyle(pulled ? theme.accent.color : theme.sub.color)
        }
        .accessibilityLabel("\(item.title), \(item.subtitle ?? "")")
        .accessibilityHint(flow.pullLabel(for: item.seed))
    }

    private var feelingsPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 64), spacing: 10)], spacing: 10) {
                    ForEach(flow.feelingTokens, id: \.self) { token in
                        let chosen = flow.isChosen(token)
                        Button { flow.toggleFeeling(token) } label: {
                            Text(token).font(NewStationFlow.isEmojiOnly(token) ? .title : .subheadline).lineLimit(1)
                                .frame(maxWidth: .infinity, minHeight: 52)
                                .background(chosen ? theme.accentSoft.color : theme.well.color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(chosen ? theme.accent.color : .clear, lineWidth: 2))
                        }
                        .buttonStyle(.plain)
                        .disabled(!chosen && flow.feelingsFull)
                        .accessibilityLabel(NewStationFlow.feelingNames[token] ?? token)
                        .accessibilityAddTraits(chosen ? .isSelected : [])
                    }
                }
                HStack {
                    TextField("Or in your words", text: Bindable(flow).wordsDraft).textFieldStyle(.roundedBorder).submitLabel(.done)
                        .onSubmit { flow.addWords() }
                    Button("Add") { flow.addWords() }.buttonStyle(.bordered).disabled(flow.feelingsFull || flow.wordsDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .padding(.horizontal, 20).padding(.bottom, 16)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private var finishPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("YOUR STATION").font(.caption.bold()).tracking(1.2).foregroundStyle(theme.sub.color)
                    pickedRow(records: nil)
                }
                field("Name", prompt: flow.stationName ?? "My late-night station", text: $name)
                field("In a few words", prompt: "Rainy Sunday, slow and warm", text: $details, axis: .vertical)
                Text("The words join your feelings, so Juke can match them. Keep it short.").font(.footnote).foregroundStyle(theme.sub.color)
            }
            .padding(.horizontal, 20).padding(.bottom, 16)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func field(_ label: String, prompt: String, text: Binding<String>, axis: Axis = .horizontal) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.subheadline.weight(.semibold)).foregroundStyle(theme.ink.color)
            TextField(prompt, text: text, axis: axis).lineLimit(1...3).padding(12)
                .background(theme.well.color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    /// The picks as removable chips. `records` limits to one kind; `nil` shows everything.
    private func pickedRow(records: Bool?) -> some View {
        let picks = flow.picks.filter { pick in
            switch (records, pick) {
            case (nil, _): true
            case (true?, .record): true
            case (false?, .feeling): true
            default: false
            }
        }
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                if picks.isEmpty { Text("Nothing yet").font(.subheadline).foregroundStyle(theme.sub.color) }
                ForEach(picks) { pick in
                    Button { flow.remove(pick) } label: {
                        HStack(spacing: 6) { Text(pick.text).lineLimit(1); Image(systemName: "xmark.circle.fill").font(.caption) }
                            .font(.subheadline.weight(.semibold)).padding(.horizontal, 12).padding(.vertical, 8)
                            .background(theme.accentSoft.color, in: Capsule())
                    }
                    .buttonStyle(.plain).foregroundStyle(theme.ink.color)
                    .accessibilityLabel("Remove \(pick.text)")
                }
            }
            .padding(.horizontal, records == nil ? 0 : 20)
        }
    }

    // MARK: Actions

    private func go(to target: NewStationPage, forward isForward: Bool) {
        forward = isForward
        withAnimation(gentle) { page = target }
    }

    private func advance() { if let next = page.next, NewStationWizard.canAdvance(from: page, flow: flow) { go(to: next, forward: true) } }

    private func back() {
        // Opened with picks already chosen (no start question): back leaves the wizard.
        if page == .first, startedWithPicks { model.coordinator.closeNewStation(); return }
        if let previous = page.previous { go(to: previous, forward: false) }
    }

    private func search() async {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitesting") {
            let titles = ["Blue in Green", "So What", "Kind of Blue", "A Love Supreme", "Take Five", "Giant Steps"]
            results = titles.enumerated().map { Radio.CrateItem(id: Radio.ID("\($0.offset)"), kind: kind, spotifyId: "fixture\($0.offset)", title: $0.element, subtitle: "Miles Davis", artworkUrl: nil, track: nil) }
            return
        }
        #endif
        guard model.session != nil else { return }
        searching = true; error = nil
        defer { searching = false }
        do { results = try await model.api.crate(kind: kind, query: query.isEmpty ? nil : query) }
        catch is CancellationError { return }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? "The crate could not be loaded." }
    }

    private func create(_ timing: JukeCoordinator.StationRequest.Timing) async {
        saving = true; error = nil
        defer { saving = false }
        do {
            let station = try await model.api.createStation(
                name: NewStationWizard.name(name),
                seeds: Array(flow.seeds.prefix(NewStationFlow.maxRecords)),
                feelings: NewStationWizard.feelings(flow.feelings, description: details)
            )
            await model.radio.loadStations()
            model.coordinator.requestStation(station.id, timing: timing)
        } catch { self.error = (error as? LocalizedError)?.errorDescription ?? "The station could not be created." }
    }
}
