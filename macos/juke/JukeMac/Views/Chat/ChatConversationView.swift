import SwiftUI

/// The chat card's content. Behaviour is unchanged from Juke Vibe: the
/// opening question, local Foundation Models or backend replies (chosen in
/// `AppModel.send()`), encrypted storage and sync through `ChatVault`, and
/// the app lock (applied by the root view).
struct ChatConversationView: View {
    @Environment(\.jukeTheme) private var theme
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @FocusState private var focused: Bool
    @State private var showingPrivacy = false

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        Text(model.openingQuestion)
                            .font(JukeFont.display(30, weight: .semibold))
                            .tracking(-0.6)
                            .lineSpacing(2)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.bottom, 14)
                            .accessibilityIdentifier("chat.openingQuestion")
                        ForEach(model.messages) { message in
                            ChatBubble(message: message, textSize: model.chatTextSize)
                        }
                        if model.isAwaitingReply { JukeTypingBubble() }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding(.horizontal, 40)
                    .padding(.top, 12)
                    .padding(.bottom, 20)
                }
                .scrollIndicators(.hidden)
                .defaultScrollAnchor(.bottom)
                .onAppear { scrollToBottom(proxy, animated: false) }
                .onChange(of: model.messages.last?.id) { _, _ in scrollToBottom(proxy) }
                .onChange(of: model.isAwaitingReply) { _, _ in scrollToBottom(proxy) }
            }
            composer
        }
        .navigationTitle("Chat")
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

    /// The current song, small; privacy and text size on the right.
    private var header: some View {
        HStack(spacing: 10) {
            VinylDisc(label: theme.accent.color, size: 22, isSpinning: model.detection.isPlaying)
            Group {
                if let track = model.detection.track {
                    Text(track.title).font(JukeFont.body(13, weight: .semibold))
                        + Text("  ·  \(track.artist)").font(JukeFont.body(13))
                } else {
                    Text("Nothing playing").font(JukeFont.body(13))
                }
            }
            .foregroundStyle(theme.sub.color)
            .lineLimit(1)
            .accessibilityIdentifier("chat.nowPlaying")
            Spacer(minLength: 12)
            Button { showingPrivacy.toggle() } label: {
                Label("Private", systemImage: "lock.fill").font(JukeFont.body(12, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(theme.sub.color)
            .help("Your conversations are encrypted")
            .accessibilityIdentifier("chat.privacy")
            .popover(isPresented: $showingPrivacy, arrowEdge: .bottom) {
                Text("Juke encrypts conversation history before storing or syncing it. Cloud chat receives only the message you deliberately send and current-track context.")
                    .font(JukeFont.body(13))
                    .frame(width: 300)
                    .padding(16)
            }
            textSizeControl
        }
        .padding(.horizontal, 24)
        .padding(.top, 18)
        .padding(.bottom, 6)
    }

    private var textSizeControl: some View {
        HStack(spacing: 0) {
            Button { model.chatTextSize -= 1 } label: { Text("A").font(JukeFont.body(11, weight: .semibold)).frame(width: 28, height: 26) }
                .disabled(model.chatTextSize <= AppModel.chatTextSizeRange.lowerBound)
                .accessibilityLabel("Smaller text")
                .accessibilityIdentifier("chat.textSmaller")
            Button { model.chatTextSize += 1 } label: { Text("A").font(JukeFont.body(16, weight: .semibold)).frame(width: 28, height: 26) }
                .disabled(model.chatTextSize >= AppModel.chatTextSizeRange.upperBound)
                .accessibilityLabel("Larger text")
                .accessibilityIdentifier("chat.textLarger")
        }
        .buttonStyle(.plain)
        .foregroundStyle(theme.ink.color)
        .jukeWell(cornerRadius: 13)
        .help("Text size (\(Int(model.chatTextSize)) pt)")
    }

    /// The composer as a well at the bottom of the card.
    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            ZStack(alignment: .topLeading) {
                if model.draft.isEmpty {
                    Text("Ask about what you're hearing…")
                        .font(.system(size: model.chatTextSize, design: .rounded))
                        .foregroundStyle(theme.sub.color)
                        .padding(.leading, 5)
                        .padding(.top, 8)
                        .allowsHitTesting(false)
                }
                TextEditor(text: Bindable(model).draft)
                    .font(.system(size: model.chatTextSize, design: .rounded))
                    .foregroundStyle(theme.ink.color)
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
            .frame(minHeight: 40, maxHeight: 96)
            .fixedSize(horizontal: false, vertical: true)
            Button { model.send() } label: {
                Image(systemName: "arrow.up").font(.system(size: 15, weight: .bold))
                    .foregroundStyle(theme.onAccent.color)
                    .frame(width: 36, height: 36)
                    .background(theme.accent.color, in: Circle())
                    .opacity(canSend ? 1 : 0.4)
                    .frame(width: JukeMetrics.minimumHitTarget, height: JukeMetrics.minimumHitTarget)
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityLabel("Send message")
            .accessibilityIdentifier("chat.send")
            .help("Send message (Return). Use Shift-Return for a new line.")
        }
        .padding(.leading, 14)
        .padding(.trailing, 4)
        .padding(.vertical, 4)
        .jukeWell()
        .overlay {
            RoundedRectangle(cornerRadius: JukeRadius.well, style: .continuous)
                .strokeBorder(focused ? theme.accent.color.opacity(0.6) : .clear, lineWidth: 1.5)
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 24)
        .padding(.top, 4)
    }

    private var canSend: Bool {
        !model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !model.isSending
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
    @Environment(\.jukeTheme) private var theme

    var body: some View {
        HStack {
            TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 0.28)) { context in
                let phase = reduceMotion ? 0 : Int(context.date.timeIntervalSinceReferenceDate * 3) % 3
                HStack(spacing: 5) {
                    ForEach(0..<3, id: \.self) { index in
                        Circle()
                            .fill(theme.sub.color)
                            .frame(width: 6, height: 6)
                            .opacity(reduceMotion || phase == index ? 0.95 : 0.35)
                            .scaleEffect(reduceMotion || phase == index ? 1 : 0.82)
                    }
                }
            }
            .frame(width: 30, height: 10)
            .padding(.horizontal, 15)
            .padding(.vertical, 12)
            .jukeWell()
            Spacer(minLength: 90)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Juke is typing")
        .accessibilityIdentifier("chat.typingIndicator")
    }
}

/// Juke's replies read as plain text on the card; your messages sit in a soft accent bubble.
private struct ChatBubble: View {
    @Environment(\.jukeTheme) private var theme
    let message: DisplayChatMessage
    let textSize: Double

    var body: some View {
        HStack {
            if message.role == .assistant { content; Spacer(minLength: 80) }
            else { Spacer(minLength: 80); content }
        }
    }

    private var content: some View {
        Text(message.content)
            .font(.system(size: textSize, design: .rounded))
            .lineSpacing(3)
            .foregroundStyle(theme.ink.color)
            .textSelection(.enabled)
            .padding(.horizontal, message.role == .assistant ? 2 : 16)
            .padding(.vertical, message.role == .assistant ? 4 : 11)
            .background(message.role == .assistant ? Color.clear : theme.accentSoft.color, in: RoundedRectangle(cornerRadius: JukeRadius.well, style: .continuous))
    }
}
