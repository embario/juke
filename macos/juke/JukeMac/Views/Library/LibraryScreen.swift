import SwiftUI

/// Library section. S2 placeholder: today's catalog search and album/artist
/// pages inside the single card. S4 replaces it with the crate (flip
/// direction: `JukeSettings.crateFlipDirection`), Songs/Artists/Albums,
/// search, "Start radio" and the New station flow, using `model.api.crate(...)`.
struct LibraryScreen: View {
    var body: some View {
        JukeCard(padding: EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8)) {
            DiscoverView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: 1040, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library.screen")
    }
}
