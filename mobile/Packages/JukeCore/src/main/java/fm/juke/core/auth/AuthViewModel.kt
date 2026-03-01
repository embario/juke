package fm.juke.core.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import fm.juke.core.network.humanReadableMessage
import kotlinx.coroutines.launch

enum class AuthMode { LOGIN, REGISTER }

data class AuthUiState(
    val mode: AuthMode = AuthMode.LOGIN,
    val username: String = "",
    val email: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val isRegistrationDisabled: Boolean = false,
    val isLoading: Boolean = false,
    val message: String? = null,
    val error: String? = null,
)

fun AuthUiState.canSubmit(): Boolean {
    if (username.trim().isEmpty() || password.isBlank()) return false
    if (isRegistrationDisabled && mode == AuthMode.REGISTER) return false
    return if (mode == AuthMode.REGISTER) {
        email.trim().isNotEmpty() && confirmPassword.isNotBlank()
    } else {
        true
    }
}

open class AuthViewModel(
    private val repository: AuthRepositoryContract,
    registrationDisabled: Boolean = false,
) : ViewModel() {

    private val registrationDisabledMessage =
        "Registration is temporarily disabled. Please try again later."

    var uiState by mutableStateOf(AuthUiState())
        private set

    init {
        if (registrationDisabled) {
            uiState = uiState.copy(isRegistrationDisabled = true, mode = AuthMode.LOGIN)
        }
    }

    fun updateUsername(value: String) {
        uiState = uiState.copy(username = value, error = null, message = null)
    }

    fun updateEmail(value: String) {
        uiState = uiState.copy(email = value, error = null, message = null)
    }

    fun updatePassword(value: String) {
        uiState = uiState.copy(password = value, error = null, message = null)
    }

    fun updateConfirmPassword(value: String) {
        uiState = uiState.copy(confirmPassword = value, error = null, message = null)
    }

    fun toggleMode() {
        if (uiState.isRegistrationDisabled) {
            uiState = uiState.copy(error = registrationDisabledMessage, message = null)
            return
        }
        uiState = uiState.copy(
            mode = if (uiState.mode == AuthMode.LOGIN) AuthMode.REGISTER else AuthMode.LOGIN,
            message = null,
            error = null,
        )
    }

    fun submit() {
        if (uiState.mode == AuthMode.LOGIN) login() else register()
    }

    private fun login() {
        val username = uiState.username.trim()
        val password = uiState.password
        if (username.isBlank()) {
            uiState = uiState.copy(error = "Username is required.")
            return
        }
        if (password.isBlank()) {
            uiState = uiState.copy(error = "Password is required.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null, message = null)
            repository.login(username, password)
                .onSuccess {
                    uiState = uiState.copy(
                        isLoading = false,
                        password = "",
                        message = "Signed in as $username",
                    )
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                }
        }
    }

    private fun register() {
        if (uiState.isRegistrationDisabled) {
            uiState = uiState.copy(error = registrationDisabledMessage, message = null)
            return
        }
        val username = uiState.username.trim()
        val email = uiState.email.trim()
        val password = uiState.password
        val confirm = uiState.confirmPassword
        if (username.isBlank()) {
            uiState = uiState.copy(error = "Username is required.")
            return
        }
        if (email.isBlank()) {
            uiState = uiState.copy(error = "Email is required.")
            return
        }
        if (password.length < 8) {
            uiState = uiState.copy(error = "Password must be at least 8 characters.")
            return
        }
        if (password != confirm) {
            uiState = uiState.copy(error = "Passwords do not match.")
            return
        }
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null, message = null)
            repository.register(username, email, password, confirm)
                .onSuccess { detail ->
                    uiState = uiState.copy(
                        isLoading = false,
                        message = detail,
                        mode = AuthMode.LOGIN,
                        password = "",
                        confirmPassword = "",
                    )
                }
                .onFailure { throwable ->
                    uiState = uiState.copy(isLoading = false, error = throwable.humanReadableMessage())
                }
        }
    }
}
