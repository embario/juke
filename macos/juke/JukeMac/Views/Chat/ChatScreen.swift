import SwiftUI

/// Chat section: one calm card. The current song sits small at the top, the
/// conversation scrolls inside the card, and the composer is a well at the bottom.
struct ChatScreen: View {
    var body: some View {
        JukeCard(padding: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0)) {
            ChatConversationView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: 760, maxHeight: .infinity)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("chat.screen")
    }
}
