import SwiftUI

/// Memories section: the single memory card (see `MemoriesView`), which also
/// hosts the guided composer.
struct MemoriesScreen: View {
    var body: some View {
        MemoriesView()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("memories.screen")
    }
}
