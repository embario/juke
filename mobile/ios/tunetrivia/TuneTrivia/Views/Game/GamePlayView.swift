//
//  GamePlayView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI
import AVFoundation

struct GamePlayView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    let sessionId: Int

    @State private var sessionDetail: SessionDetailResponse?
    @State private var currentRound: TuneTriviaRound?
    @State private var isLoading = true
    @State private var errorMessage: String?

    // Guessing state
    @State private var songGuess = ""
    @State private var artistGuess = ""
    @State private var hasSubmittedGuess = false
    @State private var isSubmitting = false

    // Trivia state
    @State private var selectedTriviaOption: String?
    @State private var hasSubmittedTrivia = false
    @State private var triviaResult: TriviaSubmitResponse?
    @State private var isSubmittingTrivia = false

    // Audio player
    @State private var audioPlayer: AVPlayer?
    @State private var isPlaying = false
    @State private var playbackProgress: Double = 0

    // Game flow
    @State private var showScoreboard = false
    @State private var isAdvancing = false
    @State private var isEndingGame = false
    @State private var awardingPlayerId: Int?

    private let tuneTriviaService = TuneTriviaService()
    private let pollTimer = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

    var isHost: Bool {
        sessionDetail?.session.hostUsername == session.profile?.username
    }

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            if isLoading && sessionDetail == nil {
                VStack(spacing: 16) {
                    TuneTriviaSpinner()
                    Text("Loading game...")
                        .foregroundColor(TuneTriviaPalette.muted)
                }
            } else if let detail = sessionDetail {
                if detail.status == .finished {
                    // Game finished - show final scoreboard
                    FinalScoreboardView(players: detail.players, sessionName: detail.name, onDone: {
                        dismiss()
                    })
                } else if let round = currentRound {
                    // Active gameplay
                    gameplayContent(round: round, detail: detail)
                } else {
                    // Waiting for round
                    VStack(spacing: 16) {
                        TuneTriviaSpinner()
                        Text("Waiting for next round...")
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                }
            } else if let error = errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundColor(TuneTriviaPalette.accent)
                    Text(error)
                        .foregroundColor(TuneTriviaPalette.muted)
                }
            }
        }
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                if isHost && sessionDetail?.status != .finished {
                    Button {
                        Task { await endGame() }
                    } label: {
                        if isEndingGame {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Text("End Game")
                        }
                    }
                    .foregroundColor(TuneTriviaPalette.accent)
                    .disabled(isEndingGame)
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showScoreboard = true
                } label: {
                    Image(systemName: "list.number")
                        .foregroundColor(TuneTriviaPalette.text)
                }
            }
        }
        .sheet(isPresented: $showScoreboard) {
            if let detail = sessionDetail {
                ScoreboardSheet(players: detail.players)
            }
        }
        .task {
            await loadSession()
        }
        .onReceive(pollTimer) { _ in
            Task { await pollSession() }
        }
        .onDisappear {
            stopAudio()
        }
    }

    @ViewBuilder
    private func gameplayContent(round: TuneTriviaRound, detail: SessionDetailResponse) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                // Error banner
                if let error = errorMessage {
                    TuneTriviaStatusBanner(message: error, variant: .error)
                        .padding(.horizontal, 24)
                        .padding(.top, 12)
                        .onTapGesture {
                            errorMessage = nil
                        }
                }

                // Round indicator
                HStack {
                    Text("Round \(round.roundNumber) of \(detail.session.maxSongs)")
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.text)

                    Spacer()

                    TuneTriviaChip(
                        label: round.status.rawValue.capitalized,
                        color: round.status == .revealed ? TuneTriviaPalette.secondary : TuneTriviaPalette.accent
                    )
                }
                .padding(.horizontal, 24)
                .padding(.top, 20)

                // Album art / mystery card
                ZStack {
                    if round.status == .revealed {
                        // Show album art
                        RoundedRectangle(cornerRadius: 20)
                            .fill(TuneTriviaPalette.panel)
                            .frame(width: 200, height: 200)
                            .overlay(
                                Image(systemName: "music.note")
                                    .font(.system(size: 60))
                                    .foregroundColor(TuneTriviaPalette.muted)
                            )
                    } else {
                        // Mystery card
                        RoundedRectangle(cornerRadius: 20)
                            .fill(
                                LinearGradient(
                                    colors: [TuneTriviaPalette.accent, TuneTriviaPalette.tertiary],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 200, height: 200)
                            .overlay(
                                Image(systemName: "questionmark")
                                    .font(.system(size: 60, weight: .bold))
                                    .foregroundColor(.white)
                            )
                    }
                }

                // Song info (if revealed)
                if round.status == .revealed {
                    VStack(spacing: 8) {
                        Text(round.trackName)
                            .font(.title2.weight(.bold))
                            .foregroundColor(TuneTriviaPalette.text)
                            .multilineTextAlignment(.center)

                        Text(round.artistName)
                            .font(.title3)
                            .foregroundColor(TuneTriviaPalette.secondary)
                    }
                    .padding(.horizontal, 24)
                }

                // Audio controls
                if round.status == .playing, let previewUrl = round.previewUrl {
                    AudioControlsView(
                        isPlaying: $isPlaying,
                        progress: $playbackProgress,
                        onToggle: { toggleAudio(url: previewUrl) }
                    )
                    .padding(.horizontal, 24)
                }

                // Award Points Section (Host Mode only, after reveal)
                if isHost && detail.session.mode == .host && round.status == .revealed {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Award Points")
                            .font(.headline)
                            .foregroundColor(TuneTriviaPalette.text)
                            .padding(.horizontal, 24)

                        ForEach(detail.players.filter { !$0.isHost }) { player in
                            AwardPointsRow(
                                player: player,
                                isAwarding: awardingPlayerId == player.id,
                                onAward: { points in
                                    Task { await awardPoints(playerId: player.id, points: points) }
                                }
                            )
                            .padding(.horizontal, 24)
                        }
                    }
                }

                // Guess form (if playing and not yet submitted)
                if round.status == .playing && !hasSubmittedGuess && !isHost {
                    TuneTriviaCard {
                        VStack(spacing: 16) {
                            Text("Your Guess")
                                .font(.headline)
                                .foregroundColor(TuneTriviaPalette.text)

                            TuneTriviaInputField(
                                label: "Song Title",
                                placeholder: "What song is this?",
                                text: $songGuess,
                                error: nil
                            )

                            TuneTriviaInputField(
                                label: "Artist",
                                placeholder: "Who sings it?",
                                text: $artistGuess,
                                error: nil
                            )

                            Button {
                                Task { await submitGuess(roundId: round.id) }
                            } label: {
                                if isSubmitting {
                                    TuneTriviaSpinner()
                                } else {
                                    Text("Submit Guess")
                                }
                            }
                            .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                            .disabled(songGuess.isEmpty && artistGuess.isEmpty || isSubmitting)
                        }
                    }
                    .padding(.horizontal, 24)
                } else if hasSubmittedGuess && round.status == .playing {
                    TuneTriviaCard(accentColor: TuneTriviaPalette.secondary) {
                        HStack {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(TuneTriviaPalette.secondary)
                            Text("Guess submitted! Waiting for reveal...")
                                .foregroundColor(TuneTriviaPalette.text)
                        }
                    }
                    .padding(.horizontal, 24)
                }

                // Trivia Question Section (shown after reveal when trivia is enabled)
                if round.status == .revealed && round.hasTrivia {
                    triviaSection(round: round, detail: detail)
                        .padding(.horizontal, 24)
                }

                // Host controls
                if isHost {
                    TuneTriviaCard {
                        VStack(spacing: 12) {
                            Text("Host Controls")
                                .font(.headline)
                                .foregroundColor(TuneTriviaPalette.text)

                            if round.status == .playing {
                                Button {
                                    Task { await revealRound() }
                                } label: {
                                    Text("Reveal Answer")
                                }
                                .buttonStyle(TuneTriviaButtonStyle(variant: .secondary))
                            } else if round.status == .revealed {
                                Button {
                                    Task { await nextRound() }
                                } label: {
                                    if isAdvancing {
                                        TuneTriviaSpinner()
                                    } else {
                                        Text(round.roundNumber < detail.session.maxSongs ? "Next Round" : "Finish Game")
                                    }
                                }
                                .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                                .disabled(isAdvancing)
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                }

                Spacer(minLength: 40)
            }
        }
    }

    // MARK: - Trivia Section

    @ViewBuilder
    private func triviaSection(round: TuneTriviaRound, detail: SessionDetailResponse) -> some View {
        let canAnswer = !isHost && detail.session.mode == .party

        TuneTriviaCard(accentColor: TuneTriviaPalette.highlight) {
            VStack(spacing: 16) {
                // Header
                HStack(spacing: 8) {
                    Image(systemName: "brain.head.profile")
                        .foregroundColor(TuneTriviaPalette.highlight)
                    Text("Bonus Trivia")
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.text)
                    Spacer()
                    Text("+50 pts")
                        .font(.caption.weight(.bold))
                        .foregroundColor(TuneTriviaPalette.highlight)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            Capsule()
                                .fill(TuneTriviaPalette.highlight.opacity(0.2))
                        )
                }

                // Question
                if let question = round.triviaQuestion {
                    Text(question)
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(TuneTriviaPalette.text)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                // Options
                if let options = round.triviaOptions {
                    if canAnswer && !hasSubmittedTrivia {
                        // Interactive options for party mode players
                        VStack(spacing: 10) {
                            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                                TriviaOptionButton(
                                    label: optionLabel(index: index),
                                    text: option,
                                    isSelected: selectedTriviaOption == option,
                                    isDisabled: isSubmittingTrivia
                                ) {
                                    selectedTriviaOption = option
                                }
                            }
                        }

                        // Submit button
                        Button {
                            Task { await submitTrivia(roundId: round.id) }
                        } label: {
                            if isSubmittingTrivia {
                                TuneTriviaSpinner()
                            } else {
                                Text("Submit Answer")
                            }
                        }
                        .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                        .disabled(selectedTriviaOption == nil || isSubmittingTrivia)
                        .padding(.top, 4)

                    } else if hasSubmittedTrivia, let result = triviaResult {
                        // Show trivia result
                        VStack(spacing: 10) {
                            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                                TriviaResultRow(
                                    label: optionLabel(index: index),
                                    text: option,
                                    isCorrectAnswer: option == result.correctAnswer,
                                    wasSelected: option == selectedTriviaOption
                                )
                            }
                        }

                        // Result message
                        HStack(spacing: 8) {
                            Image(systemName: result.correct ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(result.correct ? TuneTriviaPalette.secondary : TuneTriviaPalette.accent)
                            Text(result.correct ? "Correct! +\(result.pointsEarned) pts" : "Incorrect!")
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(result.correct ? TuneTriviaPalette.secondary : TuneTriviaPalette.accent)
                        }
                        .padding(.top, 4)

                    } else {
                        // Read-only for host or host-mode (show options without interactivity)
                        VStack(spacing: 8) {
                            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                                HStack(spacing: 8) {
                                    Text(optionLabel(index: index))
                                        .font(.caption.weight(.bold))
                                        .foregroundColor(TuneTriviaPalette.highlight)
                                        .frame(width: 24)
                                    Text(option)
                                        .font(.subheadline)
                                        .foregroundColor(TuneTriviaPalette.text)
                                    Spacer()
                                }
                                .padding(.vertical, 6)
                            }
                        }
                    }
                }
            }
        }
    }

    private func optionLabel(index: Int) -> String {
        let labels = ["A", "B", "C", "D"]
        return index < labels.count ? labels[index] : "\(index + 1)"
    }

    // MARK: - Actions

    private func loadSession() async {
        isLoading = true

        do {
            sessionDetail = try await tuneTriviaService.getSession(id: sessionId, token: session.token)
            updateCurrentRound()
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func pollSession() async {
        guard sessionDetail?.status == .playing else { return }

        do {
            let oldRound = currentRound
            sessionDetail = try await tuneTriviaService.getSession(id: sessionId, token: session.token)
            updateCurrentRound()

            // Reset guess and trivia state if round changed
            if currentRound?.id != oldRound?.id {
                hasSubmittedGuess = false
                songGuess = ""
                artistGuess = ""
                selectedTriviaOption = nil
                hasSubmittedTrivia = false
                triviaResult = nil
                stopAudio()
            }
        } catch {
            // Silently fail
        }
    }

    private func updateCurrentRound() {
        guard let detail = sessionDetail else { return }
        currentRound = detail.rounds.first { $0.status == .playing || $0.status == .revealed }
            ?? detail.rounds.last
    }

    private func submitGuess(roundId: Int) async {
        isSubmitting = true

        do {
            _ = try await tuneTriviaService.submitGuess(
                roundId: roundId,
                songGuess: songGuess.isEmpty ? nil : songGuess,
                artistGuess: artistGuess.isEmpty ? nil : artistGuess,
                token: session.token
            )
            hasSubmittedGuess = true
        } catch {
            // Handle error
        }

        isSubmitting = false
    }

    private func submitTrivia(roundId: Int) async {
        guard let answer = selectedTriviaOption else { return }

        isSubmittingTrivia = true

        do {
            let result = try await tuneTriviaService.submitTriviaAnswer(
                roundId: roundId,
                triviaGuess: answer,
                token: session.token
            )
            triviaResult = result
            hasSubmittedTrivia = true
            // Refresh session to get updated scores
            await loadSession()
        } catch {
            errorMessage = "Failed to submit trivia answer."
        }

        isSubmittingTrivia = false
    }

    private func revealRound() async {
        guard let token = session.token else { return }

        do {
            _ = try await tuneTriviaService.revealRound(sessionId: sessionId, token: token)
            await loadSession()
            stopAudio()
        } catch {
            // Handle error
        }
    }

    private func nextRound() async {
        guard let token = session.token else { return }

        isAdvancing = true

        do {
            _ = try await tuneTriviaService.nextRound(sessionId: sessionId, token: token)
            hasSubmittedGuess = false
            songGuess = ""
            artistGuess = ""
            selectedTriviaOption = nil
            hasSubmittedTrivia = false
            triviaResult = nil
            await loadSession()
        } catch {
            // Handle error
        }

        isAdvancing = false
    }

    private func endGame() async {
        guard let token = session.token else { return }

        isEndingGame = true

        do {
            _ = try await tuneTriviaService.endGame(sessionId: sessionId, token: token)
            await loadSession()
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isEndingGame = false
    }

    private func awardPoints(playerId: Int, points: Int) async {
        guard let token = session.token else { return }

        awardingPlayerId = playerId

        do {
            _ = try await tuneTriviaService.awardPoints(playerId: playerId, points: points, token: token)
            await loadSession()
        } catch {
            // Handle error
        }

        awardingPlayerId = nil
    }

    // MARK: - Audio

    private func toggleAudio(url: String) {
        if isPlaying {
            stopAudio()
        } else {
            playAudio(url: url)
        }
    }

    private func playAudio(url: String) {
        guard let audioUrl = URL(string: url) else { return }
        audioPlayer = AVPlayer(url: audioUrl)
        audioPlayer?.play()
        isPlaying = true
    }

    private func stopAudio() {
        audioPlayer?.pause()
        audioPlayer = nil
        isPlaying = false
        playbackProgress = 0
    }
}

// MARK: - Trivia Subviews

struct TriviaOptionButton: View {
    let label: String
    let text: String
    let isSelected: Bool
    let isDisabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Text(label)
                    .font(.caption.weight(.bold))
                    .foregroundColor(isSelected ? .white : TuneTriviaPalette.highlight)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle()
                            .fill(isSelected ? TuneTriviaPalette.highlight : TuneTriviaPalette.highlight.opacity(0.2))
                    )

                Text(text)
                    .font(.subheadline)
                    .foregroundColor(TuneTriviaPalette.text)
                    .multilineTextAlignment(.leading)

                Spacer()
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ? TuneTriviaPalette.highlight.opacity(0.15) : TuneTriviaPalette.panel)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        isSelected ? TuneTriviaPalette.highlight : Color.clear,
                        lineWidth: 2
                    )
            )
        }
        .disabled(isDisabled)
    }
}

struct TriviaResultRow: View {
    let label: String
    let text: String
    let isCorrectAnswer: Bool
    let wasSelected: Bool

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.caption.weight(.bold))
                .foregroundColor(iconColor)
                .frame(width: 28, height: 28)
                .background(
                    Circle()
                        .fill(iconColor.opacity(0.2))
                )

            Text(text)
                .font(.subheadline)
                .foregroundColor(TuneTriviaPalette.text)
                .multilineTextAlignment(.leading)

            Spacer()

            if isCorrectAnswer {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(TuneTriviaPalette.secondary)
            } else if wasSelected && !isCorrectAnswer {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(TuneTriviaPalette.accent)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(backgroundColor)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(borderColor, lineWidth: isCorrectAnswer || wasSelected ? 2 : 0)
        )
    }

    private var iconColor: Color {
        if isCorrectAnswer {
            return TuneTriviaPalette.secondary
        } else if wasSelected {
            return TuneTriviaPalette.accent
        }
        return TuneTriviaPalette.muted
    }

    private var backgroundColor: Color {
        if isCorrectAnswer {
            return TuneTriviaPalette.secondary.opacity(0.1)
        } else if wasSelected {
            return TuneTriviaPalette.accent.opacity(0.1)
        }
        return TuneTriviaPalette.panel
    }

    private var borderColor: Color {
        if isCorrectAnswer {
            return TuneTriviaPalette.secondary
        } else if wasSelected {
            return TuneTriviaPalette.accent
        }
        return Color.clear
    }
}

// MARK: - Existing Subviews

struct AudioControlsView: View {
    @Binding var isPlaying: Bool
    @Binding var progress: Double

    let onToggle: () -> Void

    var body: some View {
        TuneTriviaCard {
            VStack(spacing: 12) {
                // Progress bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(TuneTriviaPalette.muted.opacity(0.3))
                            .frame(height: 8)

                        RoundedRectangle(cornerRadius: 4)
                            .fill(TuneTriviaPalette.accent)
                            .frame(width: geo.size.width * progress, height: 8)
                    }
                }
                .frame(height: 8)

                // Play button
                Button(action: onToggle) {
                    Image(systemName: isPlaying ? "pause.circle.fill" : "play.circle.fill")
                        .font(.system(size: 56))
                        .foregroundColor(TuneTriviaPalette.accent)
                }

                Text(isPlaying ? "Playing..." : "Tap to play")
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
            }
        }
    }
}

struct AwardPointsRow: View {
    let player: TuneTriviaPlayer
    let isAwarding: Bool
    let onAward: (Int) -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Player info
            Circle()
                .fill(TuneTriviaPalette.secondary.opacity(0.2))
                .frame(width: 40, height: 40)
                .overlay(
                    Text(String(player.displayName.prefix(1)).uppercased())
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.secondary)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(player.displayName)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.text)

                Text("\(player.totalScore) pts")
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
            }

            Spacer()

            if isAwarding {
                ProgressView()
                    .scaleEffect(0.8)
            } else {
                // Quick award buttons
                HStack(spacing: 8) {
                    Button {
                        onAward(50)
                    } label: {
                        Text("+50")
                            .font(.caption.weight(.bold))
                            .foregroundColor(TuneTriviaPalette.secondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(TuneTriviaPalette.secondary.opacity(0.2))
                            )
                    }

                    Button {
                        onAward(100)
                    } label: {
                        Text("+100")
                            .font(.caption.weight(.bold))
                            .foregroundColor(TuneTriviaPalette.accent)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(TuneTriviaPalette.accent.opacity(0.2))
                            )
                    }

                    Button {
                        onAward(150)
                    } label: {
                        Text("+150")
                            .font(.caption.weight(.bold))
                            .foregroundColor(TuneTriviaPalette.highlight)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(TuneTriviaPalette.highlight.opacity(0.2))
                            )
                    }
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(TuneTriviaPalette.panel)
        )
    }
}

struct ScoreboardSheet: View {
    let players: [TuneTriviaPlayer]

    var sortedPlayers: [TuneTriviaPlayer] {
        players.sorted { $0.totalScore > $1.totalScore }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                TuneTriviaBackground()

                ScrollView {
                    VStack(spacing: 12) {
                        ForEach(Array(sortedPlayers.enumerated()), id: \.element.id) { index, player in
                            HStack {
                                Text("#\(index + 1)")
                                    .font(.headline)
                                    .foregroundColor(index == 0 ? TuneTriviaPalette.highlight : TuneTriviaPalette.muted)
                                    .frame(width: 40)

                                Text(player.displayName)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(TuneTriviaPalette.text)

                                Spacer()

                                Text("\(player.totalScore) pts")
                                    .font(.headline)
                                    .foregroundColor(TuneTriviaPalette.accent)
                            }
                            .padding()
                            .background(
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(TuneTriviaPalette.panel)
                            )
                        }
                    }
                    .padding(24)
                }
            }
            .navigationTitle("Scoreboard")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct FinalScoreboardView: View {
    let players: [TuneTriviaPlayer]
    let sessionName: String
    let onDone: () -> Void

    var sortedPlayers: [TuneTriviaPlayer] {
        players.sorted { $0.totalScore > $1.totalScore }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                // Trophy
                Image(systemName: "trophy.fill")
                    .font(.system(size: 80))
                    .foregroundColor(TuneTriviaPalette.highlight)
                    .padding(.top, 40)

                Text("Game Over!")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundColor(TuneTriviaPalette.text)

                Text(sessionName)
                    .font(.title3)
                    .foregroundColor(TuneTriviaPalette.muted)

                // Winner
                if let winner = sortedPlayers.first {
                    TuneTriviaCard(accentColor: TuneTriviaPalette.highlight) {
                        VStack(spacing: 8) {
                            Text("Winner")
                                .font(.subheadline)
                                .foregroundColor(TuneTriviaPalette.muted)

                            Text(winner.displayName)
                                .font(.title.weight(.bold))
                                .foregroundColor(TuneTriviaPalette.text)

                            Text("\(winner.totalScore) points")
                                .font(.title2)
                                .foregroundColor(TuneTriviaPalette.highlight)
                        }
                    }
                    .padding(.horizontal, 24)
                }

                // Full standings
                VStack(alignment: .leading, spacing: 12) {
                    Text("Final Standings")
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.text)
                        .padding(.horizontal, 24)

                    ForEach(Array(sortedPlayers.enumerated()), id: \.element.id) { index, player in
                        HStack {
                            Text("#\(index + 1)")
                                .font(.headline)
                                .foregroundColor(index == 0 ? TuneTriviaPalette.highlight : TuneTriviaPalette.muted)
                                .frame(width: 40)

                            Text(player.displayName)
                                .foregroundColor(TuneTriviaPalette.text)

                            Spacer()

                            Text("\(player.totalScore) pts")
                                .font(.headline)
                                .foregroundColor(TuneTriviaPalette.accent)
                        }
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(TuneTriviaPalette.panel)
                        )
                        .padding(.horizontal, 24)
                    }
                }

                // Done button
                Button(action: onDone) {
                    Text("Done")
                }
                .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                .padding(.horizontal, 24)
                .padding(.top, 20)

                Spacer(minLength: 40)
            }
        }
    }
}

struct GamePlayView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            GamePlayView(sessionId: 1)
                .environmentObject(SessionStore())
        }
    }
}
