//
//  AddTracksView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI

struct AddTracksView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    let sessionId: Int
    let maxSongs: Int
    let currentCount: Int

    @State private var searchQuery = ""
    @State private var searchResults: [SpotifyTrack] = []
    @State private var isSearching = false
    @State private var isAutoSelecting = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    private let tuneTriviaService = TuneTriviaService()

    var remainingSlots: Int {
        maxSongs - currentCount
    }

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            VStack(spacing: 0) {
                // Search Bar
                HStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(TuneTriviaPalette.muted)

                    TextField("Search for songs...", text: $searchQuery)
                        .textFieldStyle(.plain)
                        .submitLabel(.search)
                        .onSubmit {
                            Task { await searchTracks() }
                        }

                    if !searchQuery.isEmpty {
                        Button {
                            searchQuery = ""
                            searchResults = []
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(TuneTriviaPalette.muted)
                        }
                    }
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(TuneTriviaPalette.panel)
                )
                .padding(.horizontal, 24)
                .padding(.top, 20)

                if let error = errorMessage {
                    TuneTriviaStatusBanner(message: error, variant: .error)
                        .padding(.horizontal, 24)
                        .padding(.top, 12)
                }

                if let success = successMessage {
                    TuneTriviaStatusBanner(message: success, variant: .success)
                        .padding(.horizontal, 24)
                        .padding(.top, 12)
                }

                // Slots remaining
                HStack {
                    Text("\(remainingSlots) slots remaining")
                        .font(.caption)
                        .foregroundColor(TuneTriviaPalette.muted)

                    Spacer()

                    Button {
                        Task { await autoSelectTracks() }
                    } label: {
                        HStack(spacing: 4) {
                            if isAutoSelecting {
                                ProgressView()
                                    .scaleEffect(0.7)
                            } else {
                                Image(systemName: "wand.and.stars")
                            }
                            Text("Auto-fill")
                        }
                        .font(.caption.weight(.medium))
                        .foregroundColor(TuneTriviaPalette.secondary)
                    }
                    .disabled(remainingSlots == 0 || isAutoSelecting)
                }
                .padding(.horizontal, 24)
                .padding(.top, 16)

                // Results
                if isSearching {
                    Spacer()
                    VStack(spacing: 12) {
                        TuneTriviaSpinner()
                        Text("Searching...")
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    Spacer()
                } else if searchResults.isEmpty && !searchQuery.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "music.note.list")
                            .font(.largeTitle)
                            .foregroundColor(TuneTriviaPalette.muted)
                        Text("No results found")
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    Spacer()
                } else if searchResults.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.largeTitle)
                            .foregroundColor(TuneTriviaPalette.muted)
                        Text("Search for songs to add")
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    Spacer()
                } else {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(searchResults) { track in
                                SearchResultRow(track: track) {
                                    Task { await addTrack(track) }
                                }
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.top, 12)
                        .padding(.bottom, 40)
                    }
                }
            }
        }
        .navigationTitle("Add Tracks")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func searchTracks() async {
        guard !searchQuery.isEmpty, let token = session.token else { return }

        isSearching = true
        errorMessage = nil

        do {
            searchResults = try await tuneTriviaService.searchTracks(query: searchQuery, token: token)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "Failed to search tracks"
        }

        isSearching = false
    }

    private func addTrack(_ track: SpotifyTrack) async {
        guard let token = session.token, remainingSlots > 0 else { return }

        do {
            _ = try await tuneTriviaService.addTrack(
                sessionId: sessionId,
                trackId: track.id,
                token: token
            )
            successMessage = "Added \"\(track.name)\""

            // Remove from results
            searchResults.removeAll { $0.id == track.id }

            // Clear success after delay
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                successMessage = nil
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "Failed to add track"
        }
    }

    private func autoSelectTracks() async {
        guard let token = session.token, remainingSlots > 0 else { return }

        isAutoSelecting = true
        errorMessage = nil

        do {
            let tracks = try await tuneTriviaService.autoSelectTracks(
                sessionId: sessionId,
                count: remainingSlots,
                token: token
            )
            successMessage = "Added \(tracks.count) tracks"
            dismiss()
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "Failed to auto-select tracks"
        }

        isAutoSelecting = false
    }
}

// MARK: - Spotify Track Model

struct SpotifyTrack: Codable, Identifiable {
    let id: String
    let name: String
    let artistName: String
    let albumName: String
    let albumArtUrl: String?
    let previewUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case artistName = "artist_name"
        case albumName = "album_name"
        case albumArtUrl = "album_art_url"
        case previewUrl = "preview_url"
    }
}

struct SearchResultRow: View {
    let track: SpotifyTrack
    let onAdd: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Album art placeholder
            RoundedRectangle(cornerRadius: 8)
                .fill(TuneTriviaPalette.muted.opacity(0.2))
                .frame(width: 50, height: 50)
                .overlay(
                    Image(systemName: "music.note")
                        .foregroundColor(TuneTriviaPalette.muted)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(track.name)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.text)
                    .lineLimit(1)

                Text(track.artistName)
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
                    .lineLimit(1)
            }

            Spacer()

            Button(action: onAdd) {
                Image(systemName: "plus.circle.fill")
                    .font(.title2)
                    .foregroundColor(TuneTriviaPalette.accent)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(TuneTriviaPalette.panel)
        )
    }
}

struct AddTracksView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            AddTracksView(sessionId: 1, maxSongs: 10, currentCount: 3)
                .environmentObject(SessionStore())
        }
    }
}
