package com.juke.juke.ui.navigation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.juke.juke.core.design.JukePalette
import com.juke.juke.core.design.components.JukeBackground
import com.juke.juke.core.design.components.JukeSpinner
import com.juke.juke.ui.auth.AuthRoute
import com.juke.juke.ui.onboarding.OnboardingRoute
import com.juke.juke.ui.session.SessionUiState
import com.juke.juke.ui.session.SessionViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.juke.juke.ui.world.JukeWorldScreen
import com.juke.juke.ui.world.WorldFocus

@Composable
fun JukeApp(sessionViewModel: SessionViewModel = viewModel()) {
    val sessionState by sessionViewModel.uiState.collectAsStateWithLifecycle()
    var navigateToWorld by remember { mutableStateOf(false) }
    var worldFocus by remember { mutableStateOf<WorldFocus?>(null) }

    when (val state = sessionState) {
        SessionUiState.Loading -> Splash()
        SessionUiState.SignedOut -> {
            navigateToWorld = false
            worldFocus = null
            AuthRoute()
        }
        is SessionUiState.SignedIn -> {
            when {
                navigateToWorld -> {
                    JukeWorldScreen(
                        token = state.snapshot.token,
                        focus = worldFocus,
                        onExit = {
                            navigateToWorld = false
                            worldFocus = null
                        },
                        onLogout = sessionViewModel::logout,
                    )
                }
                !state.onboardingCompleted -> {
                    OnboardingRoute(
                        sessionToken = state.snapshot.token,
                        onComplete = { location ->
                            worldFocus = location?.let {
                                WorldFocus(
                                    lat = it.lat,
                                    lng = it.lng,
                                    username = state.snapshot.username,
                                )
                            }
                            navigateToWorld = true
                        },
                    )
                }
                else -> HomeScreen(
                    session = state.snapshot,
                    onOpenWorld = {
                        worldFocus = null
                        navigateToWorld = true
                    },
                    onLogout = sessionViewModel::logout,
                )
            }
        }
    }
}

@Composable
private fun Splash() {
    JukeBackground {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            JukeSpinner()
            Text(
                text = "Spinning up your crates...",
                style = MaterialTheme.typography.bodyMedium,
                color = JukePalette.Muted,
            )
        }
    }
}
