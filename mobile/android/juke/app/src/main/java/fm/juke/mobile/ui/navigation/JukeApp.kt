package fm.juke.mobile.ui.navigation

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
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.design.components.JukeBackground
import fm.juke.mobile.core.design.components.JukeSpinner
import fm.juke.mobile.ui.auth.AuthRoute
import fm.juke.mobile.ui.onboarding.OnboardingRoute
import fm.juke.mobile.ui.session.SessionUiState
import fm.juke.mobile.ui.session.SessionViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.juke.mobile.ui.world.JukeWorldScreen
import fm.juke.mobile.ui.world.WorldFocus

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
                    OnboardingRoute(onComplete = { location ->
                        worldFocus = location?.let {
                            WorldFocus(
                                lat = it.lat,
                                lng = it.lng,
                                username = state.snapshot.username,
                            )
                        }
                        navigateToWorld = true
                    })
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
