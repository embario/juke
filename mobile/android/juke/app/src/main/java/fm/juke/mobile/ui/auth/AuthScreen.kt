package fm.juke.mobile.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.juke.core.auth.AuthMode
import fm.juke.core.auth.AuthUiState
import fm.juke.core.auth.canSubmit
import fm.juke.mobile.core.design.JukeTheme
import fm.juke.mobile.core.design.components.JukeBackground
import fm.juke.mobile.core.design.components.JukeButton
import fm.juke.mobile.core.design.components.JukeCard
import fm.juke.mobile.core.design.components.JukeChip
import fm.juke.mobile.core.design.components.JukeInputField
import fm.juke.mobile.core.design.components.JukeSpinner
import fm.juke.mobile.core.design.components.JukeStatusBanner
import fm.juke.mobile.core.design.components.JukeStatusVariant

@Composable
fun AuthRoute(viewModel: AuthViewModel = viewModel()) {
    val state = viewModel.uiState
    AuthScreen(
        state = state,
        onUsernameChange = viewModel::updateUsername,
        onEmailChange = viewModel::updateEmail,
        onPasswordChange = viewModel::updatePassword,
        onConfirmPasswordChange = viewModel::updateConfirmPassword,
        onToggleMode = viewModel::toggleMode,
        onSubmit = viewModel::submit,
    )
}

@Composable
fun AuthScreen(
    state: AuthUiState,
    onUsernameChange: (String) -> Unit,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onConfirmPasswordChange: (String) -> Unit,
    onToggleMode: () -> Unit,
    onSubmit: () -> Unit,
) {
    val scrollState = rememberScrollState()
    JukeBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = 24.dp, vertical = 40.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "Welcome to Juke",
                    style = MaterialTheme.typography.displayLarge,
                )
                Text(
                    text = "Log in to sync your library or create an account to broadcast your sonic fingerprint.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                )
            }
            JukeCard {
                Column(
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    if (state.isRegistrationDisabled) {
                        JukeStatusBanner(
                            message = "Registration is temporarily disabled while email delivery is offline.",
                            variant = JukeStatusVariant.WARNING,
                        )
                    } else {
                        AuthModeToggle(mode = state.mode, onToggleMode = onToggleMode)
                    }
                    JukeInputField(
                        label = "Username",
                        value = state.username,
                        onValueChange = onUsernameChange,
                        placeholder = "your-handle",
                    )
                    if (state.mode == AuthMode.REGISTER) {
                        JukeInputField(
                            label = "Email",
                            value = state.email,
                            onValueChange = onEmailChange,
                            placeholder = "you@juke.fm",
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        )
                    }
                    JukeInputField(
                        label = "Password",
                        value = state.password,
                        onValueChange = onPasswordChange,
                        placeholder = "••••••••",
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        visualTransformation = PasswordVisualTransformation(),
                    )
                    if (state.mode == AuthMode.REGISTER) {
                        JukeInputField(
                            label = "Confirm Password",
                            value = state.confirmPassword,
                            onValueChange = onConfirmPasswordChange,
                            placeholder = "Match the magic",
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            visualTransformation = PasswordVisualTransformation(),
                        )
                    }
                    JukeStatusBanner(
                        message = state.message,
                        variant = JukeStatusVariant.SUCCESS,
                    )
                    JukeStatusBanner(
                        message = state.error,
                        variant = JukeStatusVariant.ERROR,
                    )
                    JukeButton(
                        onClick = onSubmit,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp),
                        enabled = state.canSubmit() && !state.isLoading,
                    ) {
                        if (state.isLoading) {
                            Spacer(modifier = Modifier.weight(1f))
                            JukeSpinner()
                            Spacer(modifier = Modifier.weight(1f))
                        } else {
                            Text(text = if (state.mode == AuthMode.LOGIN) "Log In" else "Create Account")
                        }
                    }
                    Text(
                        text = "By continuing you agree to keep the vibes immaculate.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
                    )
                }
            }
        }
    }
}

@Preview
@Composable
private fun AuthScreenPreview() {
    JukeTheme {
        AuthScreen(
            state = AuthUiState(),
            onUsernameChange = {},
            onEmailChange = {},
            onPasswordChange = {},
            onConfirmPasswordChange = {},
            onToggleMode = {},
            onSubmit = {},
        )
    }
}

@Composable
private fun AuthModeToggle(
    mode: AuthMode,
    onToggleMode: () -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        AuthMode.values().forEach { candidate ->
            val label = if (candidate == AuthMode.LOGIN) "Log In" else "Register"
            JukeChip(
                label = label,
                selected = mode == candidate,
                modifier = Modifier.weight(1f),
                onClick = {
                    if (mode != candidate) onToggleMode()
                },
            )
        }
    }
}
