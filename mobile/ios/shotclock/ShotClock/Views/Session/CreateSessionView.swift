import SwiftUI

struct CreateSessionView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = CreateSessionViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            SCBackground()

            ScrollView {
                VStack(spacing: 20) {
                    // Title
                    SCInputField(
                        label: "Session Title",
                        placeholder: "e.g. Friday Night Power Hour",
                        text: $viewModel.title
                    )

                    // Tracks per player
                    SCCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Tracks per Player")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.text)
                            HStack {
                                Text("\(viewModel.tracksPerPlayer)")
                                    .font(.title3.bold())
                                    .foregroundColor(SCPalette.accent)
                                    .frame(width: 30)
                                Slider(
                                    value: Binding(
                                        get: { Double(viewModel.tracksPerPlayer) },
                                        set: { viewModel.tracksPerPlayer = Int($0) }
                                    ),
                                    in: 1...10,
                                    step: 1
                                )
                                .tint(SCPalette.accent)
                            }
                        }
                    }

                    // Max tracks
                    SCCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Max Tracks")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.text)
                            HStack {
                                Text("\(viewModel.maxTracks)")
                                    .font(.title3.bold())
                                    .foregroundColor(SCPalette.accent)
                                    .frame(width: 30)
                                Slider(
                                    value: Binding(
                                        get: { Double(viewModel.maxTracks) },
                                        set: { viewModel.maxTracks = Int($0) }
                                    ),
                                    in: 10...60,
                                    step: 5
                                )
                                .tint(SCPalette.accent)
                            }
                        }
                    }

                    // Seconds per track
                    SCCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Seconds per Track")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.text)
                            HStack {
                                Text("\(viewModel.secondsPerTrack)s")
                                    .font(.title3.bold())
                                    .foregroundColor(SCPalette.accent)
                                    .frame(width: 44)
                                Slider(
                                    value: Binding(
                                        get: { Double(viewModel.secondsPerTrack) },
                                        set: { viewModel.secondsPerTrack = Int($0) }
                                    ),
                                    in: 30...120,
                                    step: 10
                                )
                                .tint(SCPalette.accent)
                            }
                        }
                    }

                    // Transition clip
                    SCCard {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Transition Sound")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.text)

                            FlowLayout(spacing: 8) {
                                ForEach(CreateSessionViewModel.transitionClips, id: \.0) { clip in
                                    SCChip(
                                        label: clip.1,
                                        isActive: viewModel.transitionClip == clip.0
                                    ) {
                                        viewModel.transitionClip = clip.0
                                        SoundPlayer.shared.play(clip.0)
                                    }
                                }
                            }
                        }
                    }

                    // Trivia mode toggle
                    SCCard {
                        Toggle(isOn: $viewModel.hideTrackOwners) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Trivia Mode")
                                    .font(.subheadline.bold())
                                    .foregroundColor(SCPalette.text)
                                Text("Hide who added each track")
                                    .font(.caption)
                                    .foregroundColor(SCPalette.muted)
                            }
                        }
                        .tint(SCPalette.accent)
                    }

                    SCStatusBanner(message: viewModel.errorMessage, variant: .error)

                    // Create button
                    Button {
                        Task {
                            if let _ = await viewModel.createSession(token: session.token) {
                                dismiss()
                            }
                        }
                    } label: {
                        if viewModel.isLoading {
                            SCSpinner()
                        } else {
                            Text("Create Session")
                        }
                    }
                    .buttonStyle(SCButtonStyle(variant: .primary))
                    .disabled(viewModel.isLoading)
                    .padding(.top, 8)
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 24)
            }
        }
        .navigationTitle("New Session")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}

// MARK: - Flow Layout for chips

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrange(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x - spacing)
        }

        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}

#Preview {
    NavigationStack {
        CreateSessionView()
            .environmentObject(SessionStore())
    }
}
