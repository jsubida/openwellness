package edu.openwellness.mobile.feature.auth.presentation.login

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError
import edu.openwellness.mobile.feature.auth.domain.AuthRepository
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateEmail
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateOtpCode
import edu.openwellness.mobile.feature.auth.presentation.util.toUiText
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Login flow VM. Send ALWAYS advances to [LoginStep.EnterCode] on success
 * (anti-enumeration). Verify success persists tokens in the repo and emits
 * [LoginEvent.NavigateToHome]. A 429 sets the authoritative resend cooldown.
 *
 * SavedStateHandle persists step, email, and the remaining cooldown only —
 * never the OTP code.
 */
class LoginViewModel(
    private val authRepository: AuthRepository,
    private val validateEmail: ValidateEmail,
    private val validateOtpCode: ValidateOtpCode,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val _state = MutableStateFlow(restoreState())
    val state = _state.asStateFlow()

    private val _events = Channel<LoginEvent>()
    val events = _events.receiveAsFlow()

    private var cooldownJob: Job? = null

    init {
        val restored = _state.value
        if (restored.step == LoginStep.EnterCode && restored.resendInSeconds > 0) {
            startCooldown(restored.resendInSeconds)
        }
    }

    fun onAction(action: LoginAction) {
        when (action) {
            is LoginAction.OnEmailChange -> {
                savedStateHandle[KEY_EMAIL] = action.email
                _state.update { it.copy(email = action.email, emailError = null) }
            }
            is LoginAction.OnCodeChange ->
                _state.update { it.copy(code = action.code, codeError = null, error = null) }
            LoginAction.OnSendCodeClick -> sendCode(isResend = false)
            LoginAction.OnResendClick -> sendCode(isResend = true)
            LoginAction.OnVerifyClick -> verify()
            LoginAction.OnBackToEmail -> {
                savedStateHandle[KEY_STEP] = LoginStep.EnterEmail.name
                _state.update {
                    it.copy(step = LoginStep.EnterEmail, code = "", codeError = null, error = null)
                }
            }
            LoginAction.OnErrorDismiss -> _state.update { it.copy(error = null) }
        }
    }

    private fun sendCode(isResend: Boolean) {
        if (_state.value.isLoading) return
        if (isResend && !_state.value.canResend) return

        val email = _state.value.email
        when (val valid = validateEmail(email)) {
            is Result.Error -> {
                _state.update { it.copy(emailError = valid.error.toUiText()) }
                return
            }
            is Result.Success -> Unit
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null, emailError = null) }
            when (val result = authRepository.sendLoginCode(email)) {
                is Result.Success -> {
                    savedStateHandle[KEY_STEP] = LoginStep.EnterCode.name
                    _state.update {
                        it.copy(
                            isLoading = false,
                            step = LoginStep.EnterCode,
                            code = "",
                            codeError = null,
                            error = null,
                        )
                    }
                    startCooldown(result.data.resendAfterSeconds.toInt())
                }
                is Result.Error -> {
                    _state.update { it.copy(isLoading = false) }
                    handleAuthError(result.error)
                }
            }
        }
    }

    private fun verify() {
        if (_state.value.isLoading) return

        val code = _state.value.code
        when (val valid = validateOtpCode(code)) {
            is Result.Error -> {
                _state.update { it.copy(codeError = valid.error.toUiText()) }
                return
            }
            is Result.Success -> Unit
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null, codeError = null) }
            when (val result = authRepository.verifyLoginCode(_state.value.email, code)) {
                is Result.Success -> {
                    _state.update { it.copy(isLoading = false) }
                    _events.send(LoginEvent.NavigateToHome)
                }
                is Result.Error -> {
                    _state.update { it.copy(isLoading = false) }
                    handleAuthError(result.error)
                }
            }
        }
    }

    private fun handleAuthError(error: AuthError) {
        if (error is AuthError.RateLimited) {
            startCooldown(error.retryAfterSeconds.toInt())
        }
        _state.update { it.copy(error = error.toUiText()) }
    }

    private fun startCooldown(seconds: Int) {
        cooldownJob?.cancel()
        if (seconds <= 0) {
            savedStateHandle[KEY_RESEND] = 0
            _state.update { it.copy(resendInSeconds = 0, canResend = true) }
            return
        }
        cooldownJob = viewModelScope.launch {
            var remaining = seconds
            savedStateHandle[KEY_RESEND] = remaining
            _state.update { it.copy(resendInSeconds = remaining, canResend = false) }
            while (remaining > 0) {
                delay(1000)
                remaining--
                savedStateHandle[KEY_RESEND] = remaining
                _state.update { it.copy(resendInSeconds = remaining, canResend = remaining == 0) }
            }
        }
    }

    private fun restoreState(): LoginState {
        val step = savedStateHandle.get<String>(KEY_STEP)
            ?.let { runCatching { LoginStep.valueOf(it) }.getOrNull() }
            ?: LoginStep.EnterEmail
        val remaining = savedStateHandle.get<Int>(KEY_RESEND) ?: 0
        return LoginState(
            step = step,
            email = savedStateHandle[KEY_EMAIL] ?: "",
            resendInSeconds = remaining,
            canResend = remaining == 0,
        )
    }

    private companion object {
        const val KEY_STEP = "login_step"
        const val KEY_EMAIL = "login_email"
        const val KEY_RESEND = "login_resend_in"
    }
}
