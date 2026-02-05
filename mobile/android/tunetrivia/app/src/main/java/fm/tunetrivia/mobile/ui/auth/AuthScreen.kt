package fm.tunetrivia.mobile.ui.auth

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette
import fm.tunetrivia.mobile.core.design.components.TuneTriviaBackground
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButton
import fm.tunetrivia.mobile.core.design.components.TuneTriviaButtonVariant
import fm.tunetrivia.mobile.core.design.components.TuneTriviaCard
import fm.tunetrivia.mobile.core.design.components.TuneTriviaInputField
import fm.tunetrivia.mobile.core.design.components.TuneTriviaSpinner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusBanner
import fm.tunetrivia.mobile.core.design.components.TuneTriviaStatusVariant

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

    TuneTriviaBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .systemBarsPadding(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(modifier = Modifier.height(60.dp))

            Text(
                text = "TuneTrivia",
                style = MaterialTheme.typography.displayLarge,
                color = TuneTriviaPalette.Text,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Name That Tune!",
                style = MaterialTheme.typography.bodyMedium,
                color = TuneTriviaPalette.Muted,
            )

            Spacer(modifier = Modifier.height(32.dp))

            TuneTriviaCard {
                // Registration disabled warning
                if (state.isRegistrationDisabled && isRegister) {
                    TuneTriviaStatusBanner(
                        message = "Registration is temporarily disabled.",
                        variant = TuneTriviaStatusVariant.WARNING,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                }

                // Success message
                TuneTriviaStatusBanner(
                    message = state.message,
                    variant = TuneTriviaStatusVariant.SUCCESS,
                )
                if (state.message != null) Spacer(modifier = Modifier.height(12.dp))

                // Error message
                TuneTriviaStatusBanner(
                    message = state.error,
                    variant = TuneTriviaStatusVariant.ERROR,
                )
                if (state.error != null) Spacer(modifier = Modifier.height(12.dp))

                // Form fields
                TuneTriviaInputField(
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
                    TuneTriviaInputField(
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
                TuneTriviaInputField(
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
                    TuneTriviaInputField(
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
                        TuneTriviaSpinner()
                    }
                } else {
                    TuneTriviaButton(
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

            TuneTriviaButton(
                onClick = onToggleMode,
                variant = TuneTriviaButtonVariant.LINK,
                fillMaxWidth = false,
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp),
            ) {
                Text(
                    text = if (isRegister) {
                        "Already have an account? Sign In"
                    } else {
                        "Don't have an account? Sign Up"
                    },
                )
            }
        }
    }
}
