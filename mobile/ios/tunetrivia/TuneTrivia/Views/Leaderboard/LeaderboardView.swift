//
//  LeaderboardView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI

struct LeaderboardView: View {
    @State private var entries: [LeaderboardEntry] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    private let tuneTriviaService = TuneTriviaService()

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            if isLoading {
                VStack(spacing: 16) {
                    TuneTriviaSpinner()
                    Text("Loading leaderboard...")
                        .foregroundColor(TuneTriviaPalette.muted)
                }
            } else if let error = errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundColor(TuneTriviaPalette.accent)
                    Text(error)
                        .foregroundColor(TuneTriviaPalette.muted)
                    Button("Try Again") {
                        Task { await loadLeaderboard() }
                    }
                    .buttonStyle(TuneTriviaButtonStyle(variant: .secondary))
                }
                .padding(24)
            } else if entries.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "trophy")
                        .font(.system(size: 60))
                        .foregroundColor(TuneTriviaPalette.muted)
                    Text("No scores yet")
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.text)
                    Text("Be the first to play and get on the leaderboard!")
                        .font(.subheadline)
                        .foregroundColor(TuneTriviaPalette.muted)
                        .multilineTextAlignment(.center)
                }
                .padding(24)
            } else {
                ScrollView {
                    VStack(spacing: 12) {
                        // Top 3 podium
                        if entries.count >= 3 {
                            PodiumView(
                                first: entries[0],
                                second: entries[1],
                                third: entries[2]
                            )
                            .padding(.horizontal, 24)
                            .padding(.top, 20)
                        }

                        // Rest of leaderboard
                        ForEach(Array(entries.dropFirst(3).enumerated()), id: \.element.id) { index, entry in
                            LeaderboardRow(entry: entry, rank: index + 4)
                                .padding(.horizontal, 24)
                        }

                        Spacer(minLength: 40)
                    }
                }
            }
        }
        .navigationTitle("Leaderboard")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadLeaderboard()
        }
    }

    private func loadLeaderboard() async {
        isLoading = true
        errorMessage = nil

        do {
            entries = try await tuneTriviaService.getLeaderboard()
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

struct PodiumView: View {
    let first: LeaderboardEntry
    let second: LeaderboardEntry
    let third: LeaderboardEntry

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            // Second place
            PodiumPlace(entry: second, rank: 2, height: 100, color: TuneTriviaPalette.muted)

            // First place
            PodiumPlace(entry: first, rank: 1, height: 140, color: TuneTriviaPalette.highlight)

            // Third place
            PodiumPlace(entry: third, rank: 3, height: 80, color: TuneTriviaPalette.tertiary)
        }
    }
}

struct PodiumPlace: View {
    let entry: LeaderboardEntry
    let rank: Int
    let height: CGFloat
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            // Avatar
            Circle()
                .fill(color.opacity(0.2))
                .frame(width: 50, height: 50)
                .overlay(
                    Text(String(entry.displayName.prefix(1)).uppercased())
                        .font(.headline)
                        .foregroundColor(color)
                )

            // Name
            Text(entry.displayName)
                .font(.caption.weight(.medium))
                .foregroundColor(TuneTriviaPalette.text)
                .lineLimit(1)

            // Score
            Text("\(entry.totalScore)")
                .font(.subheadline.weight(.bold))
                .foregroundColor(color)

            // Podium
            RoundedRectangle(cornerRadius: 8)
                .fill(color.opacity(0.3))
                .frame(height: height)
                .overlay(
                    Text("\(rank)")
                        .font(.title.weight(.bold))
                        .foregroundColor(color)
                )
        }
        .frame(maxWidth: .infinity)
    }
}

struct LeaderboardRow: View {
    let entry: LeaderboardEntry
    let rank: Int

    var body: some View {
        HStack(spacing: 12) {
            Text("#\(rank)")
                .font(.headline)
                .foregroundColor(TuneTriviaPalette.muted)
                .frame(width: 40, alignment: .leading)

            Circle()
                .fill(TuneTriviaPalette.secondary.opacity(0.2))
                .frame(width: 40, height: 40)
                .overlay(
                    Text(String(entry.displayName.prefix(1)).uppercased())
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(TuneTriviaPalette.secondary)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(entry.displayName)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.text)

                Text("\(entry.totalGames) games played")
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(entry.totalScore)")
                    .font(.headline)
                    .foregroundColor(TuneTriviaPalette.accent)

                Text("pts")
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(TuneTriviaPalette.panel)
        )
    }
}

struct LeaderboardView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            LeaderboardView()
        }
    }
}
