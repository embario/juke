import SwiftUI

struct ChatView: View {
    @Environment(VibeAppModel.self) private var model
    @FocusState private var focused: Bool
    @AppStorage("vibe.chatTextSize") private var textSize = 17.0
    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("LISTENING QUESTION").font(.caption.bold()).tracking(1.4).foregroundStyle(model.atmosphere.primary)
                            Text(model.question).font(.title2.weight(.semibold))
                        }.padding(.bottom, 8)
                        ForEach(model.messages) { line in
                            HStack { if line.role == "user" { Spacer(minLength: 42) }; Text(line.content).font(.system(size: textSize)).padding(13).background(line.role == "user" ? model.atmosphere.primary.opacity(0.2) : Color(.secondarySystemBackground).opacity(0.86), in: RoundedRectangle(cornerRadius: 17)); if line.role != "user" { Spacer(minLength: 42) } }
                        }
                        if model.isSending { ProgressView().controlSize(.small) }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding()
                }.onChange(of: model.messages.count) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
            }
            HStack(alignment: .bottom) {
                TextField("Ask about what you're hearing…", text: Bindable(model).draft, axis: .vertical).lineLimit(1...4).padding(12).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 17)).focused($focused)
                Button { Task { await model.send() } } label: { Image(systemName: "arrow.up").frame(width: 32, height: 32) }.buttonStyle(.borderedProminent).buttonBorderShape(.circle).tint(model.atmosphere.primary).disabled(model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }.padding(.horizontal).padding(.bottom, 8)
        }.navigationTitle("Chat").onAppear { focused = true }
    }
}
