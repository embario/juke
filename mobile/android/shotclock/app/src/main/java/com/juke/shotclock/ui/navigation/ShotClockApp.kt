package com.juke.shotclock.ui.navigation

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
import com.juke.shotclock.core.design.ShotClockPalette
import com.juke.shotclock.core.design.components.ShotClockBackground
import com.juke.shotclock.core.design.components.ShotClockSpinner
import com.juke.shotclock.ui.auth.AuthRoute
import fm.juke.core.session.AppSessionUiState
import fm.juke.core.session.AppSessionViewModel
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun ShotClockApp(sessionViewModel: AppSessionViewModel = viewModel()) {
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
    ShotClockBackground {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            ShotClockSpinner()
            Text(
                text = "Warming up the shots...",
                style = MaterialTheme.typography.bodyMedium,
                color = ShotClockPalette.Muted,
            )
        }
    }
}
