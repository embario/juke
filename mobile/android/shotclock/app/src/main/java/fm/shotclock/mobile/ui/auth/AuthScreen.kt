package fm.shotclock.mobile.ui.auth

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.juke.core.auth.AuthMode
import fm.juke.core.auth.AuthUiState
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.*

@Composable
fun AuthRoute(viewModel: AuthViewModel = viewModel()) {
    AuthScreen(
        state = viewModel.uiState,
        onUsernameChange = viewModel::updateUsername,
        onEmailChange = viewModel::updateEmail,
        onPasswordChange = viewModel::updatePassword,
        onConfirmPasswordChange = viewModel::updateConfirmPassword,
        onToggleMode = viewModel::toggleMode,
        onSubmit = viewModel::submit,
    )
}

@Composable
private fun AuthScreen(
    state: AuthUiState,
    onUsernameChange: (String) -> Unit,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onConfirmPasswordChange: (String) -> Unit,
    onToggleMode: () -> Unit,
    onSubmit: () -> Unit,
) {
    val focusManager = LocalFocusManager.current
    val isRegister = state.mode == AuthMode.REGISTER

    ShotClockBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .systemBarsPadding(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(modifier = Modifier.height(60.dp))

            // Logo with neon glow
            Text(
                text = "ShotClock",
                style = MaterialTheme.typography.displayLarge,
                color = ShotClockPalette.Accent,
                modifier = Modifier.shadow(
                    elevation = 0.dp,
                    ambientColor = ShotClockPalette.Accent.copy(alpha = 0.5f),
                ),
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Power Hour, powered up.",
                style = MaterialTheme.typography.bodyMedium,
                color = ShotClockPalette.Muted,
            )

            Spacer(modifier = Modifier.height(32.dp))

            ShotClockCard {
                // Mode toggle chips
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    ShotClockChip(
                        label = "Login",
                        selected = !isRegister,
                        onClick = { if (isRegister) onToggleMode() },
                    )
                    ShotClockChip(
                        label = "Register",
                        selected = isRegister,
                        onClick = { if (!isRegister) onToggleMode() },
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Registration disabled warning
                if (state.isRegistrationDisabled && isRegister) {
                    ShotClockStatusBanner(
                        message = "Registration is temporarily disabled.",
                        variant = SCStatusVariant.WARNING,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                }

                // Success message
                ShotClockStatusBanner(
                    message = state.message,
                    variant = SCStatusVariant.SUCCESS,
                )
                if (state.message != null) Spacer(modifier = Modifier.height(12.dp))

                // Error message
                ShotClockStatusBanner(
                    message = state.error,
                    variant = SCStatusVariant.ERROR,
                )
                if (state.error != null) Spacer(modifier = Modifier.height(12.dp))

                // Form fields
                ShotClockInputField(
                    label = "Username",
                    value = state.username,
                    onValueChange = onUsernameChange,
                    placeholder = "Enter username",
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Text,
                        imeAction = if (isRegister) ImeAction.Next else ImeAction.Next,
                    ),
                )

                if (isRegister) {
                    Spacer(modifier = Modifier.height(16.dp))
                    ShotClockInputField(
                        label = "Email",
                        value = state.email,
                        onValueChange = onEmailChange,
                        placeholder = "Enter email",
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Email,
                            imeAction = ImeAction.Next,
                        ),
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))
                ShotClockInputField(
                    label = "Password",
                    value = state.password,
                    onValueChange = onPasswordChange,
                    placeholder = "Enter password",
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = if (isRegister) ImeAction.Next else ImeAction.Done,
                    ),
                    keyboardActions = if (!isRegister) {
                        KeyboardActions(onDone = {
                            focusManager.clearFocus()
                            onSubmit()
                        })
                    } else KeyboardActions.Default,
                )

                if (isRegister) {
                    Spacer(modifier = Modifier.height(16.dp))
                    ShotClockInputField(
                        label = "Confirm Password",
                        value = state.confirmPassword,
                        onValueChange = onConfirmPasswordChange,
                        placeholder = "Re-enter password",
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Done,
                        ),
                        keyboardActions = KeyboardActions(onDone = {
                            focusManager.clearFocus()
                            onSubmit()
                        }),
                    )
                }

                Spacer(modifier = Modifier.height(24.dp))

                if (state.isLoading) {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        ShotClockSpinner()
                    }
                } else {
                    ShotClockButton(
                        onClick = {
                            focusManager.clearFocus()
                            onSubmit()
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(text = if (isRegister) "Create Account" else "Sign In")
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}
