import SwiftUI

struct AddTracksView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel: AddTracksViewModel

    init(sessionId: String) {
        _viewModel = StateObject(wrappedValue: AddTracksViewModel(sessionId: sessionId))
    }

    var body: some View {
        ZStack {
            SCBackground()

            VStack(spacing: 0) {
                // Search bar
                HStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(SCPalette.muted)
                    TextField("Search Spotify...", text: $viewModel.searchQuery)
                        .foregroundColor(SCPalette.text)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .onSubmit {
                            viewModel.search(token: session.token)
                        }
                    if !viewModel.searchQuery.isEmpty {
                        Button {
                            viewModel.searchQuery = ""
                            viewModel.searchResults = []
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(SCPalette.muted)
                        }
                    }
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 16)
                .background(SCPalette.panelAlt.opacity(0.65))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(SCPalette.border, lineWidth: 1)
                )
                .cornerRadius(14)
                .padding(.horizontal, 24)
                .padding(.top, 16)
                .padding(.bottom, 12)

                // Content
                if viewModel.isSearching {
                    Spacer()
                    SCSpinner()
                    Spacer()
                } else if viewModel.searchResults.isEmpty && !viewModel.searchQuery.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "music.note.list")
                            .font(.system(size: 40))
                            .foregroundColor(SCPalette.muted.opacity(0.5))
                        Text("No results found")
                            .font(.headline)
                            .foregroundColor(SCPalette.muted)
                        Text("Try a different search term")
                            .font(.subheadline)
                            .foregroundColor(SCPalette.muted.opacity(0.7))
                    }
                    Spacer()
                } else if viewModel.searchResults.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 40))
                            .foregroundColor(SCPalette.muted.opacity(0.5))
                        Text("Search for tracks")
                            .font(.headline)
                            .foregroundColor(SCPalette.muted)
                        Text("Find songs on Spotify to add to your Power Hour")
                            .font(.subheadline)
                            .foregroundColor(SCPalette.muted.opacity(0.7))
                            .multilineTextAlignment(.center)
                    }
                    .padding(.horizontal, 40)
                    Spacer()
                } else {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(viewModel.searchResults) { track in
                                SearchResultRow(
                                    track: track,
                                    isAdding: viewModel.addingTrackIds.contains(track.pk),
                                    isAdded: viewModel.addedTrackIds.contains(track.pk)
                                ) {
                                    Task {
                                        await viewModel.addTrack(track, token: session.token)
                                    }
                                }
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.bottom, 32)
                    }
                }

                if let error = viewModel.errorMessage {
                    SCStatusBanner(message: error, variant: .error)
                        .padding(.horizontal, 24)
                        .padding(.bottom, 16)
                }
            }
        }
        .navigationTitle("Add Tracks")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .onChange(of: viewModel.searchQuery) { _ in
            viewModel.search(token: session.token)
        }
    }
}

// MARK: - Search Result Row

struct SearchResultRow: View {
    let track: CatalogTrack
    let isAdding: Bool
    let isAdded: Bool
    let onAdd: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(track.name)
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(SCPalette.text)
                        .lineLimit(1)
                    if track.explicit {
                        Text("E")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(SCPalette.background)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(SCPalette.muted)
                            .cornerRadius(3)
                    }
                }
                HStack(spacing: 8) {
                    if let artist = track.artistNames, !artist.isEmpty {
                        Text(artist)
                            .lineLimit(1)
                    }
                    if let album = track.albumName, !album.isEmpty {
                        Text(album)
                            .lineLimit(1)
                    }
                }
                .font(.caption)
                .foregroundColor(SCPalette.muted)
            }

            Spacer()

            Text(track.formattedDuration)
                .font(.caption)
                .foregroundColor(SCPalette.muted)

            Button(action: onAdd) {
                if isAdding {
                    ProgressView()
                        .scaleEffect(0.7)
                        .tint(SCPalette.accent)
                } else if isAdded {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(SCPalette.success)
                } else {
                    Image(systemName: "plus.circle.fill")
                        .foregroundColor(SCPalette.accent)
                }
            }
            .disabled(isAdding || isAdded)
            .frame(width: 30)
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 14)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(SCPalette.panel.opacity(0.6))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(SCPalette.border, lineWidth: 1)
                )
        )
    }
}

#Preview {
    NavigationStack {
        AddTracksView(sessionId: "test-id")
            .environmentObject(SessionStore())
    }
}
