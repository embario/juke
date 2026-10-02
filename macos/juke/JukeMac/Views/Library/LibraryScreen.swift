import SwiftUI

/// Library section: flip through the crate (Songs, Artists, Albums, or dig
/// for anything) and start a station from any record.
///
/// "Open the album/artist" on the radio sleeve sets
/// `coordinator.libraryFocus`; this screen brings that record to the front
/// (searching by its title when it is not in the personal crate) and clears it.
struct LibraryScreen: View {
    @Environment(AppModel.self) private var model
    @State private var cache = CrateServicesCache()

    var body: some View {
        LibraryContent(services: cache.services(api: model.api))
    }
}

private struct LibraryContent: View {
    let services: CrateServices
    @Environment(AppModel.self) private var model
    @Environment(JukeSettings.self) private var settings
    @Environment(\.jukeTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var browser: CrateBrowser
    @State private var isStarting = false
    @State private var startError: String?

    init(services: CrateServices) {
        self.services = services
        _browser = State(initialValue: CrateBrowser(source: services.crate))
    }

    private var mode: CrateMode { CrateMode(settings.crateFlipDirection) }

    var body: some View {
        JukeCard(padding: EdgeInsets(top: 18, leading: 32, bottom: 20, trailing: 32)) {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 0) {
                    Text("Library")
                        .font(JukeFont.display(24, weight: .bold))
                        .tracking(-0.5)
                        .accessibilityAddTraits(.isHeader)
                    Text("Flip through the crate. Start a station from anything.")
                        .font(JukeFont.body(14))
                        .foregroundStyle(theme.sub.color)
                }
                CrateToolbar(browser: browser)
                // Return on the front record starts radio from it.
                CratePanel(browser: browser, onReturn: { _ in Task { await startRadio() } })
                focusRow
            }
        }
        .frame(width: mode.cardWidth)
        .animation(reduceMotion ? nil : JukeMotion.easeOutSoft(0.55), value: mode)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .crateArtworkTint(browser.focusedItem, model: model)
        .task(id: model.coordinator.libraryFocus) {
            await browser.appear(coordinator: model.coordinator)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library.screen")
    }

    private var focusRow: some View {
        HStack(spacing: 14) {
            Spacer(minLength: 0)
            CrateFocusCaption(item: browser.focusedItem)
            Button {
                Task { await startRadio() }
            } label: {
                HStack(spacing: 6) {
                    if isStarting {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "play.fill").font(.system(size: 12, weight: .bold))
                    }
                    Text("Start radio")
                }
            }
            .buttonStyle(JukeAccentButtonStyle())
            .disabled(browser.focusedItem == nil || isStarting)
            .accessibilityHint(browser.focusedItem.map { "Starts a station from \($0.title) after the current song" } ?? "")
            .accessibilityIdentifier("library.startRadio")
            Spacer(minLength: 0)
        }
        .frame(minHeight: 46)
        .overlay(alignment: .trailing) {
            if let startError {
                Text(startError)
                    .font(JukeFont.body(12))
                    .foregroundStyle(theme.sub.color)
                    .lineLimit(2)
                    .frame(maxWidth: 220, alignment: .trailing)
                    .accessibilityIdentifier("library.startError")
            }
        }
    }

    private func startRadio() async {
        guard let item = browser.focusedItem, !isStarting else { return }
        isStarting = true
        startError = nil
        defer { isStarting = false }
        do {
            try await StationStarter(creator: services.stations, coordinator: model.coordinator)
                .start(seeds: [item.seed], feelings: [])
            model.section = .radio
        } catch is CancellationError {
        } catch {
            startError = error.localizedDescription
        }
    }
}
