import SwiftUI

/// Memories section. S2 hosts the existing catalog and composer inside the
/// single card; S5 restyles them into the photo-print layout from the design.
struct MemoriesScreen: View {
    var body: some View {
        JukeCard(padding: EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8)) {
            MemoriesView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: 1040, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("memories.screen")
    }
}
