import SwiftUI

/// Songs · Artists · Albums, the search field and the flip switch, in one row
/// above the crate (Library and New Station's Records step).
struct CrateToolbar: View {
    let browser: CrateBrowser
    @Environment(JukeSettings.self) private var settings

    var body: some View {
        HStack(spacing: 8) {
            CrateKindPicker(browser: browser)
            CrateSearchField(browser: browser, width: CrateMode(settings.crateFlipDirection).searchWidth)
                .padding(.leading, 8)
            Spacer(minLength: 8)
            CrateFlipSwitch(direction: Bindable(settings).crateFlipDirection)
        }
    }
}

struct CrateKindPicker: View {
    let browser: CrateBrowser
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 2) {
            ForEach(CrateBrowser.kinds, id: \.self) { kind in
                let selected = browser.kind == kind
                Button {
                    Task { await browser.select(kind: kind) }
                } label: {
                    Text(CrateBrowser.label(for: kind))
                        .font(JukeFont.body(14, weight: .semibold))
                        .foregroundStyle(selected ? theme.card.color : theme.ink.color)
                        .padding(.horizontal, 12)
                        .frame(minHeight: 40)
                        .background(selected ? theme.ink.color : .clear, in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier("crate.kind.\(kind.rawValue)")
            }
        }
        .animation(JukeMotion.control(reduceMotion: reduceMotion), value: browser.kind)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Show")
    }
}

/// "Dig for anything": a borderless field with a bottom rule.
struct CrateSearchField: View {
    let browser: CrateBrowser
    var width: CGFloat
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(theme.sub.color)
                .accessibilityHidden(true)
            TextField("Dig for anything", text: Binding(get: { browser.query }, set: { browser.setQuery($0) }))
                .textFieldStyle(.plain)
                .font(JukeFont.body(15))
                .accessibilityLabel("Dig for")
                .accessibilityIdentifier("crate.search")
            if !browser.query.isEmpty {
                Button {
                    browser.setQuery("")
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(theme.sub.color)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
            }
        }
        .frame(width: width, height: 40)
        .overlay(alignment: .bottom) { Rectangle().fill(theme.line).frame(height: 1) }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.55), value: width)
    }
}

/// The small switch above the crate. It reads and writes the same setting as
/// Settings, so the two always agree.
struct CrateFlipSwitch: View {
    @Binding var direction: CrateFlipDirection
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 2) {
            ForEach(CrateFlipDirection.allCases) { option in
                let selected = option == direction
                Button {
                    direction = option
                } label: {
                    CrateFlipIcon(direction: option)
                        .stroke(selected ? theme.ink.color : theme.sub.color, style: StrokeStyle(lineWidth: 1.6, lineJoin: .round))
                        .frame(width: 20, height: 20)
                        .frame(width: 40, height: 36)
                        .background(selected ? theme.card.color : .clear, in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .help("Flip records \(option.label.lowercased())")
                .accessibilityLabel("Flip records \(option.label.lowercased())")
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier("crate.flip.\(option.rawValue)")
            }
        }
        .padding(3)
        .background(theme.well.color, in: Capsule())
        .animation(JukeMotion.control(reduceMotion: reduceMotion), value: direction)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("How records flip")
    }
}

/// The prototype's two glyphs: a record between two angled ones (side to side)
/// and a record with two behind it (front to back). Drawn in a 24-unit box.
struct CrateFlipIcon: Shape {
    var direction: CrateFlipDirection

    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 24
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * s, y: rect.minY + y * s) }
        var path = Path()
        switch direction {
        case .sideToSide:
            path.addLines([p(9, 6), p(15, 6), p(15, 18), p(9, 18)]); path.closeSubpath()
            path.addLines([p(3, 8), p(7, 9), p(7, 15), p(3, 16)]); path.closeSubpath()
            path.addLines([p(21, 8), p(17, 9), p(17, 15), p(21, 16)]); path.closeSubpath()
        case .frontToBack:
            path.addLines([p(7, 10), p(17, 10), p(17, 20), p(7, 20)]); path.closeSubpath()
            path.move(to: p(8.5, 7)); path.addLine(to: p(15.5, 7))
            path.move(to: p(10, 4)); path.addLine(to: p(14, 4))
        }
        return path
    }
}

/// The crate with its loading, empty and error states.
struct CratePanel: View {
    let browser: CrateBrowser
    var pulledIDs: Set<String> = []
    var onActivateFront: ((Radio.CrateItem) -> Void)?
    var activateLabel: (Radio.CrateItem) -> String = { _ in "Pull this record" }
    @Environment(JukeSettings.self) private var settings
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        CrateView(
            items: browser.items,
            focus: Bindable(browser).focus,
            mode: CrateMode(settings.crateFlipDirection),
            pulledIDs: pulledIDs,
            onActivateFront: onActivateFront,
            activateLabel: activateLabel
        )
        .overlay { stateOverlay }
    }

    @ViewBuilder
    private var stateOverlay: some View {
        switch browser.phase {
        case .loading where browser.items.isEmpty, .idle:
            ProgressView().controlSize(.small).accessibilityLabel("Loading the crate")
        case .failed(let message):
            VStack(spacing: 10) {
                Text("The crate didn’t open.").font(JukeFont.body(15, weight: .semibold))
                Text(message).font(JukeFont.body(13)).foregroundStyle(theme.sub.color).multilineTextAlignment(.center)
                Button("Try again") { Task { await browser.reload() } }
                    .buttonStyle(JukeWellButtonStyle())
                    .accessibilityIdentifier("crate.retry")
            }
            .frame(maxWidth: 360)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("crate.error")
        case .loaded where browser.items.isEmpty:
            Text(browser.trimmedQuery.isEmpty
                 ? "Your crate is empty for now. Dig for anything above."
                 : "Nothing in this crate for “\(browser.trimmedQuery)”.")
                .font(JukeFont.body(15))
                .foregroundStyle(theme.sub.color)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
                .accessibilityIdentifier("crate.empty")
        default:
            EmptyView()
        }
    }
}

/// The focused record's title and subtitle, centred under the crate.
struct CrateFocusCaption: View {
    let item: Radio.CrateItem?
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        VStack(spacing: 0) {
            Text(item?.title ?? " ")
                .font(JukeFont.body(18, weight: .bold))
                .lineLimit(1)
                .accessibilityIdentifier("crate.focusTitle")
            Text(item?.subtitle ?? " ")
                .font(JukeFont.body(14))
                .foregroundStyle(theme.sub.color)
                .lineLimit(1)
        }
        .multilineTextAlignment(.center)
        .contentTransition(.opacity)
        .animation(.easeOut(duration: 0.2), value: item?.id)
    }
}

extension View {
    /// Tints the theme towards the record in front, cross-fading, and hands
    /// the colour back to the playing track when the crate goes away.
    func crateArtworkTint(_ item: Radio.CrateItem?, model: AppModel) -> some View {
        onChange(of: item?.artworkUrl, initial: true) { _, _ in
            guard let url = item?.artworkURL else { return }
            model.artwork.update(artworkURL: url, enabled: model.settings.artworkTintEnabled)
        }
        .onDisappear { model.syncArtwork() }
    }
}
