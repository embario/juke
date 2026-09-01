import SwiftUI

struct VibeChatView: View {
    @Environment(AppModel.self) private var model
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("LISTENING QUESTION").font(.caption.weight(.bold)).tracking(1.6).foregroundStyle(model.atmosphere.primary)
                            Text(model.openingQuestion).font(.system(size: 30, weight: .medium, design: .rounded)).textSelection(.enabled)
                        }
                        .padding(.bottom, 18)
                        ForEach(model.messages) { message in ChatBubble(message: message) }
                        if model.isSending { ProgressView().controlSize(.small).padding(.leading, 8) }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(34).frame(maxWidth: 780)
                }
                .onChange(of: model.messages.count) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
            }
            composer
        }
        .navigationTitle("Vibe")
        .onAppear { focused = true }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 12) {
            TextField("Ask about what you're hearing…", text: Bindable(model).draft, axis: .vertical)
                .textFieldStyle(.plain).lineLimit(1...5).padding(13).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                .focused($focused).onSubmit { Task { await model.send() } }
            Button { Task { await model.send() } } label: { Image(systemName: "arrow.up").font(.headline).frame(width: 34, height: 34) }
                .buttonStyle(.borderedProminent).buttonBorderShape(.circle).tint(model.atmosphere.primary)
                .disabled(model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isSending)
        }.padding(18).background(.ultraThinMaterial)
    }
}

private struct ChatBubble: View {
    let message: DisplayChatMessage
    var body: some View {
        HStack {
            if message.role == .assistant { content; Spacer(minLength: 90) }
            else { Spacer(minLength: 90); content }
        }
    }
    private var content: some View {
        Text(message.content).textSelection(.enabled).padding(.horizontal, 16).padding(.vertical, 12)
            .background(message.role == .assistant ? AnyShapeStyle(.regularMaterial) : AnyShapeStyle(Color.accentColor.opacity(0.2)), in: RoundedRectangle(cornerRadius: 17))
    }
}
