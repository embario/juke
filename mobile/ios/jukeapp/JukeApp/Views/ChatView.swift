import SwiftUI

struct ChatView: View {
    @Environment(VibeAppModel.self) private var model
    @FocusState private var focused: Bool
    @Environment(\.jukeTheme) private var theme
    @AppStorage("vibe.chatTextSize") private var textSize = 17.0

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("LISTENING QUESTION").font(.caption.bold()).tracking(1.4).foregroundStyle(theme.accent.color)
                        Text(model.question).font(.title2.weight(.semibold))
                    }.padding(.bottom, 8)
                    ForEach(model.messages) { line in
                        HStack {
                            if line.role == "user" { Spacer(minLength: 42) }
                            Text(line.content).font(.system(size: textSize)).foregroundStyle(theme.ink.color).padding(13)
                                .background(line.role == "user" ? theme.accentSoft.color : theme.card.color, in: RoundedRectangle(cornerRadius: 17))
                            if line.role != "user" { Spacer(minLength: 42) }
                        }
                    }
                    if model.isSending { ProgressView().controlSize(.small) }
                    Color.clear.frame(height: 1).id("bottom")
                }.padding()
            }
            // Dragging the list down or tapping it puts the keyboard away so the tab bar is reachable again.
            .scrollDismissesKeyboard(.interactively)
            .onTapGesture { focused = false }
            .onChange(of: model.messages.count) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
            .onChange(of: focused) { _, isFocused in if isFocused { withAnimation { proxy.scrollTo("bottom") } } }
        }
        // The composer is the only bottom inset on this screen (the now-playing pill is
        // hidden here), so the message list ends exactly above it and above the keyboard.
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .navigationTitle("Chat")
        #if DEBUG
        .onAppear { if ProcessInfo.processInfo.arguments.contains("--uitesting-focus-chat") { focused = true } }
        #endif
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Own both controls in this inset: the system keyboard toolbar can
            // occupy the same trailing space as Send on compact phones.
            if focused {
                Button { focused = false } label: {
                    Text("Done")
                        .font(.body.weight(.semibold))
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                }
                    .accessibilityLabel("Dismiss keyboard")
                    .accessibilityIdentifier("chat.dismissKeyboard")
            }
            HStack(alignment: .bottom, spacing: 12) {
                TextField("Ask about what you're hearing…", text: Bindable(model).draft, axis: .vertical)
                    .lineLimit(1...4).padding(12)
                    .background(theme.well.color, in: RoundedRectangle(cornerRadius: 17))
                    .focused($focused)
                    .accessibilityIdentifier("chat.draft")
                Button { Task { await model.send() } } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 17))
                        .frame(width: 32, height: 32)
                }
                    .buttonStyle(.borderedProminent).buttonBorderShape(.circle).tint(model.atmosphere.primary)
                    .accessibilityLabel("Send message")
                    .accessibilityIdentifier("chat.send")
                    .disabled(!ChatComposer.canSend(draft: model.draft, isSending: model.isSending))
            }
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.bar)
    }
}
