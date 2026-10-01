import SwiftUI

/// Chat section. S2 hosts the existing encrypted conversation inside the
/// single card; S5 restyles it in the same language.
struct ChatScreen: View {
    var body: some View {
        JukeCard(padding: EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4)) {
            ChatConversationView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: 860, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("chat.screen")
    }
}
