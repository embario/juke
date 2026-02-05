package fm.tunetrivia.mobile.ui.navigation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.ui.auth.AuthRoute
import fm.tunetrivia.mobile.ui.session.AppSessionUiState
import fm.tunetrivia.mobile.ui.session.AppSessionViewModel
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun TuneTriviaApp(sessionViewModel: AppSessionViewModel = viewModel()) {
    val sessionState by sessionViewModel.uiState.collectAsStateWithLifecycle()
    when (val state = sessionState) {
        AppSessionUiState.Loading -> Splash()
        AppSessionUiState.SignedOut -> AuthRoute()
        is AppSessionUiState.SignedIn -> HomeScreen(
            session = state.snapshot,
            onLogout = sessionViewModel::logout,
        )
    }
}

@Composable
private fun Splash() {
    TuneTriviaBackground {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            TuneTriviaSpinner()
            Text(
                text = "Warming up the tunes...",
                style = MaterialTheme.typography.bodyMedium,
                color = TuneTriviaPalette.Muted,
            )
        }
    }
}
