import AppKit
import SwiftUI

/// A button with a separate press-and-hold action (the reference's `press`):
/// releasing before 450 ms runs `action`; holding runs `onHold` once and the
/// release is swallowed. Keyboard and VoiceOver activation run `action`; the
/// hold action is also offered as a named accessibility action.
struct HoldableButton<Label: View>: View {
    let holdName: String
    let action: () -> Void
    let onHold: () -> Void
    @ViewBuilder var label: Label

    @State private var tracker = HoldTracker()

    var body: some View {
        Button {
            if tracker.consumeFired() { return }
            action()
        } label: {
            label
        }
        .buttonStyle(HoldDetectingStyle(tracker: tracker, onHold: onHold))
        .accessibilityAction(named: Text(holdName)) { onHold() }
    }
}

@MainActor
final class HoldTracker {
    var fired = false
    var task: Task<Void, Never>?

    func consumeFired() -> Bool {
        defer { fired = false }
        return fired
    }
}

private struct HoldDetectingStyle: ButtonStyle {
    let tracker: HoldTracker
    let onHold: () -> Void

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.85 : 1)
            .onChange(of: configuration.isPressed) { _, pressed in
                tracker.task?.cancel()
                guard pressed else { return }
                tracker.fired = false
                tracker.task = Task { @MainActor in
                    try? await Task.sleep(for: RadioGesture.holdDelay)
                    guard !Task.isCancelled else { return }
                    tracker.fired = true
                    onHold()
                }
            }
    }
}

/// Square or round album art with a theme-coloured placeholder. Images are
/// kept in a small in-memory cache, so dial thumbnails do not reload while
/// the dial moves.
struct RadioArtwork: View {
    @Environment(\.jukeTheme) private var theme
    let url: URL?
    var cornerRadius: CGFloat = JukeRadius.sleeve
    @State private var image: NSImage?

    var body: some View {
        ZStack {
            Rectangle().fill(theme.base.color)
            if let image {
                Image(nsImage: image).resizable().scaledToFill()
            } else if url == nil {
                Image(systemName: "music.note")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.75))
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .task(id: url) {
            image = nil
            guard let url else { return }
            image = await RadioImageCache.shared.image(for: url)
        }
        .accessibilityHidden(true)
    }
}

/// In-memory artwork cache shared by the radio card.
@MainActor
final class RadioImageCache {
    static let shared = RadioImageCache()
    private let cache = NSCache<NSURL, NSImage>()
    private var inFlight: [URL: Task<NSImage?, Never>] = [:]

    init() { cache.countLimit = 120 }

    func image(for url: URL) async -> NSImage? {
        if let cached = cache.object(forKey: url as NSURL) { return cached }
        if let running = inFlight[url] { return await running.value }
        let task = Task<NSImage?, Never> {
            guard let (data, response) = try? await URLSession.shared.data(from: url),
                  (response as? HTTPURLResponse).map({ (200..<300).contains($0.statusCode) }) ?? true,
                  data.count < 8_000_000 else { return nil }
            return NSImage(data: data)
        }
        inFlight[url] = task
        let image = await task.value
        inFlight[url] = nil
        if let image { cache.setObject(image, forKey: url as NSURL) }
        return image
    }
}

/// Uppercase section label used in the station sheet.
struct RadioSheetLabel: View {
    @Environment(\.jukeTheme) private var theme
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(JukeFont.body(12, weight: .bold))
            .tracking(1.4)
            .foregroundStyle(theme.sub.color)
            .accessibilityAddTraits(.isHeader)
    }
}

/// A reaction chip: an emoji, or words in quotes.
struct ReactionChip: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let reaction: String
    let isOn: Bool
    var height: CGFloat = 36
    let toggle: () -> Void

    var body: some View {
        let isWords = !RadioController.isEmoji(reaction)
        Button(action: toggle) {
            Text(isWords ? "“\(Self.short(reaction))”" : reaction)
                .font(isWords ? JukeFont.body(13) : .system(size: 17))
                .lineLimit(1)
                .truncationMode(.tail)
                .foregroundStyle(theme.ink.color)
                .padding(.horizontal, isWords ? 12 : 0)
                .frame(minWidth: height, minHeight: height, maxHeight: height)
                .fixedSize()
                .background(isOn ? theme.accentSoft.color : .clear, in: Capsule())
                .overlay(Capsule().strokeBorder(isOn ? theme.accent.color : theme.line, lineWidth: 1.5))
                .contentShape(Capsule())
                .scaleEffect(isOn ? 1.06 : 1)
                .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.3), value: isOn)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isOn ? "Remove \(reaction)" : "Feels \(reaction)")
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }

    /// Long words are shortened on the chip (about 180 pt).
    static func short(_ text: String) -> String {
        text.count > 22 ? String(text.prefix(21)) + "…" : text
    }
}

/// Round icon button (play, skip, save, dial arrows).
struct RadioIconLabel: View {
    @Environment(\.jukeTheme) private var theme
    let systemName: String
    var size: CGFloat = 44
    var iconSize: CGFloat = 18
    var style: Style = .plain

    enum Style { case accent, well, plain }

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: iconSize, weight: .semibold))
            .foregroundStyle(style == .accent ? theme.onAccent.color : (style == .plain ? theme.sub.color : theme.ink.color))
            .frame(width: size, height: size)
            .background(background, in: Circle())
            .contentShape(Circle())
    }

    private var background: Color {
        switch style {
        case .accent: theme.accent.color
        case .well: theme.well.color
        case .plain: .clear
        }
    }
}
