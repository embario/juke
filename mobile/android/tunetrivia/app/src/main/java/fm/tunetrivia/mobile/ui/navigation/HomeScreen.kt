package fm.tunetrivia.mobile.ui.navigation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButton
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButtonVariant
import fm.tunetrivia.mobile.core.design.components.TuneTriviaCard
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusBanner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusVariant
import fm.tunetrivia.mobile.data.local.SessionSnapshot
import fm.tunetrivia.mobile.model.SessionStatus
import fm.tunetrivia.mobile.model.TuneTriviaSession
import fm.tunetrivia.mobile.ui.session.home.HomeViewModel

@Composable
fun HomeScreen(
    session: SessionSnapshot,
    onLogout: () -> Unit,
) {
    val navController = rememberNavController()
    NavHost(navController = navController, startDestination = "home") {
        homeRoute(session, onLogout, navController)
        createRoute(navController)
        joinRoute(navController, session)
        lobbyRoute(navController, session)
        leaderboardRoute(navController)
        addTracksRoute(navController)
        gameRoute(navController, session)
    }
}

private fun NavGraphBuilder.homeRoute(
    session: SessionSnapshot,
    onLogout: () -> Unit,
    navController: NavController,
) {
    composable("home") {
        val viewModel: HomeViewModel = viewModel()
        val state by viewModel.uiState
        LaunchedEffect(Unit) {
            viewModel.loadSessions()
        }

        TuneTriviaBackground(modifier = Modifier.fillMaxSize()) {
            Box(modifier = Modifier.fillMaxSize()) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 24.dp)
                        .systemBarsPadding()
                        .padding(top = 20.dp, bottom = 120.dp),
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                text = "TuneTrivia",
                                style = MaterialTheme.typography.headlineLarge,
                                color = TuneTriviaPalette.Text,
                            )
                            Text(
                                text = "Welcome, ${session.username}!",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TuneTriviaPalette.Muted,
                            )
                        }
                        TuneTriviaButton(
                            onClick = onLogout,
                            variant = TuneTriviaButtonVariant.LINK,
                            fillMaxWidth = false,
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 6.dp),
                        ) {
                            Text(text = "Logout")
                        }
                    }

                    if (state.error != null) {
                        TuneTriviaStatusBanner(
                            message = state.error,
                            variant = TuneTriviaStatusVariant.ERROR,
                        )
                    }

                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "My Games",
                                style = MaterialTheme.typography.titleLarge,
                                color = TuneTriviaPalette.Text,
                            )
                            if (state.isLoading) {
                                TuneTriviaSpinner()
                            }
                        }

                        if (!state.isLoading && state.sessions.isEmpty()) {
                            TuneTriviaCard(accentColor = TuneTriviaPalette.Secondary) {
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Text(
                                        text = "No games yet",
                                        style = MaterialTheme.typography.titleMedium,
                                        color = TuneTriviaPalette.Text,
                                    )
                                    Text(
                                        text = "Create a new game or join one with a code!",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = TuneTriviaPalette.Muted,
                                    )
                                }
                            }
                        } else {
                            state.sessions.forEach { sessionItem ->
                                SessionCard(
                                    session = sessionItem,
                                    onClick = {
                                        val target = if (sessionItem.status == SessionStatus.LOBBY) {
                                            "lobby/${sessionItem.id}"
                                        } else {
                                            "game/${sessionItem.id}"
                                        }
                                        navController.navigate(target)
                                    },
                                )
                            }
                        }
                    }

                    TuneTriviaCard {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                text = "Global Leaderboard",
                                style = MaterialTheme.typography.titleMedium,
                                color = TuneTriviaPalette.Text,
                            )
                            Text(
                                text = "See top players worldwide",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TuneTriviaPalette.Muted,
                            )
                        }
                    }
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
                    ) {
                        TuneTriviaButton(
                            onClick = { navController.navigate("leaderboard") },
                            variant = TuneTriviaButtonVariant.LINK,
                            fillMaxWidth = false,
                        ) {
                            Text(text = "Open Leaderboard")
                        }
                    }
                }

                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp)
                        .padding(bottom = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    TuneTriviaButton(
                        onClick = { navController.navigate("create") },
                    ) {
                        Text(text = "+ Create Game")
                    }
                    TuneTriviaButton(
                        onClick = { navController.navigate("join") },
                        variant = TuneTriviaButtonVariant.LINK,
                    ) {
                        Text(text = "Join with Code")
                    }
                }
            }
        }
    }
}

private fun NavGraphBuilder.createRoute(navController: NavController) {
    composable("create") {
        fm.tunetrivia.mobile.ui.session.create.CreateSessionScreen(
            onBack = { navController.popBackStack() },
            onCreated = { sessionId ->
                navController.navigate("lobby/$sessionId") {
                    popUpTo("home")
                }
            },
        )
    }
}

private fun NavGraphBuilder.joinRoute(navController: NavController, session: SessionSnapshot) {
    composable("join") {
        fm.tunetrivia.mobile.ui.session.join.JoinSessionScreen(
            isAuthenticated = session.token.isNotBlank(),
            onBack = { navController.popBackStack() },
            onJoined = { sessionId ->
                navController.navigate("lobby/$sessionId") {
                    popUpTo("home")
                }
            },
        )
    }
}

private fun NavGraphBuilder.lobbyRoute(navController: NavController, session: SessionSnapshot) {
    composable("lobby/{sessionId}") { backStackEntry ->
        val sessionId = backStackEntry.arguments?.getString("sessionId")?.toIntOrNull() ?: return@composable
        fm.tunetrivia.mobile.ui.session.lobby.SessionLobbyScreen(
            sessionId = sessionId,
            currentUsername = session.username,
            onBack = { navController.popBackStack() },
            onStartGame = { navController.navigate("game/$sessionId") },
            onAddTracks = { remaining ->
                navController.navigate("add-tracks/$sessionId/$remaining")
            },
        )
    }
}

private fun NavGraphBuilder.addTracksRoute(navController: NavController) {
    composable("add-tracks/{sessionId}/{remaining}") { backStackEntry ->
        val sessionId = backStackEntry.arguments?.getString("sessionId")?.toIntOrNull() ?: return@composable
        val remaining = backStackEntry.arguments?.getString("remaining")?.toIntOrNull() ?: 0
        fm.tunetrivia.mobile.ui.session.tracks.AddTracksScreen(
            sessionId = sessionId,
            remainingSlots = remaining,
            onBack = { navController.popBackStack() },
        )
    }
}

private fun NavGraphBuilder.leaderboardRoute(navController: NavController) {
    composable("leaderboard") {
        fm.tunetrivia.mobile.ui.leaderboard.LeaderboardScreen(
            onBack = { navController.popBackStack() },
        )
    }
}

private fun NavGraphBuilder.gameRoute(navController: NavController, session: SessionSnapshot) {
    composable("game/{sessionId}") { backStackEntry ->
        val sessionId = backStackEntry.arguments?.getString("sessionId")?.toIntOrNull() ?: return@composable
        fm.tunetrivia.mobile.ui.session.game.GamePlayScreen(
            sessionId = sessionId,
            currentUsername = session.username,
            onBack = { navController.popBackStack() },
        )
    }
}

@Composable
private fun SessionCard(
    session: TuneTriviaSession,
    onClick: () -> Unit,
) {
    val accent = when (session.status) {
        SessionStatus.LOBBY -> TuneTriviaPalette.Secondary
        SessionStatus.PLAYING -> TuneTriviaPalette.Accent
        SessionStatus.PAUSED -> TuneTriviaPalette.Highlight
        SessionStatus.FINISHED -> TuneTriviaPalette.Muted
    }

    Box(modifier = Modifier.clickable(onClick = onClick)) {
        TuneTriviaCard(accentColor = accent) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = session.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = TuneTriviaPalette.Text,
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(
                        text = session.mode.name.lowercase().replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodySmall,
                        color = TuneTriviaPalette.Muted,
                    )
                    Text(
                        text = session.status.raw.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                        color = TuneTriviaPalette.Muted,
                    )
                }
            }
        }
    }
}
