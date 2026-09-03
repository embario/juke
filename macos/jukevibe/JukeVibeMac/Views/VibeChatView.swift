import SwiftUI

struct VibeChatView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
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
                        if model.isAwaitingReply { JukeTypingBubble() }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(34).frame(maxWidth: 780)
                }
                .defaultScrollAnchor(.bottom)
                .onAppear { scrollToBottom(proxy, animated: false) }
                .onChange(of: model.messages.last?.id) { _, _ in scrollToBottom(proxy) }
                .onChange(of: model.isAwaitingReply) { _, _ in scrollToBottom(proxy) }
            }
            composer
        }
        .navigationTitle("Vibe")
        .task(id: scenePhase) {
            guard scenePhase == .active else {
                focused = false
                return
            }
            try? await Task.sleep(for: .milliseconds(120))
            guard !Task.isCancelled else { return }
            focused = true
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 12) {
            ZStack(alignment: .topLeading) {
                if model.draft.isEmpty && !focused {
                    Text("Ask about what you're hearing…")
                        .foregroundStyle(.tertiary)
                        .padding(.leading, 5)
                        .padding(.top, 8)
                        .allowsHitTesting(false)
                }
                TextEditor(text: Bindable(model).draft)
                    .font(.body)
                    .scrollContentBackground(.hidden)
                    .focused($focused)
                    .accessibilityLabel("Message Juke")
                    .accessibilityIdentifier("chat.composer")
                    .onKeyPress(keys: [.return], phases: .down) { press in
                        guard !press.modifiers.contains(.shift) else { return .ignored }
                        model.send()
                        return .handled
                    }
            }
            .frame(height: 58)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
            Button { model.send() } label: { Image(systemName: "arrow.up").font(.headline).frame(width: 34, height: 34) }
                .buttonStyle(.borderedProminent).buttonBorderShape(.circle).tint(model.atmosphere.primary)
                .disabled(model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isSending)
                .accessibilityLabel("Send message")
                .accessibilityIdentifier("chat.send")
                .help("Send message (Return). Use Shift-Return for a new line.")
        }
        .overlay(alignment: .topLeading) {
            if let syncNotice = model.syncNotice {
                Label(syncNotice, systemImage: "icloud.slash")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 20)
                    .offset(y: -17)
                    .accessibilityIdentifier("chat.syncStatus")
            }
        }
        .padding(18).background(.ultraThinMaterial)
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy, animated: Bool = true) {
        Task { @MainActor in
            await Task.yield()
            if animated {
                withAnimation(.easeOut(duration: 0.22)) { proxy.scrollTo("bottom", anchor: .bottom) }
            } else {
                proxy.scrollTo("bottom", anchor: .bottom)
            }
        }
    }
}

private struct JukeTypingBubble: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack {
            TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 0.28)) { context in
                let phase = reduceMotion ? 0 : Int(context.date.timeIntervalSinceReferenceDate * 3) % 3
                HStack(spacing: 5) {
                    ForEach(0..<3, id: \.self) { index in
                        Circle()
                            .fill(.secondary)
                            .frame(width: 6, height: 6)
                            .opacity(reduceMotion || phase == index ? 0.95 : 0.35)
                            .scaleEffect(reduceMotion || phase == index ? 1 : 0.82)
                    }
                }
            }
            .frame(width: 30, height: 10)
            .padding(.horizontal, 15)
            .padding(.vertical, 11)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 17))
            Spacer(minLength: 90)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Juke is typing")
        .accessibilityIdentifier("chat.typingIndicator")
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
