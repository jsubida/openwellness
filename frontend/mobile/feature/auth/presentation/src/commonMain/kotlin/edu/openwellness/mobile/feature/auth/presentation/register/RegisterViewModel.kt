package edu.openwellness.mobile.feature.auth.presentation.register

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError
import edu.openwellness.mobile.feature.auth.domain.AuthRepository
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateEmail
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateOtpCode
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateParticipant
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
 * Registration flow VM — mirrors [LoginViewModel] but step 1 also validates the
 * participant id and calls the registration endpoints. SavedStateHandle persists
 * step, email, participant, and remaining cooldown — never the OTP code.
 */
class RegisterViewModel(
    private val authRepository: AuthRepository,
    private val validateEmail: ValidateEmail,
    private val validateParticipant: ValidateParticipant,
    private val validateOtpCode: ValidateOtpCode,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val _state = MutableStateFlow(restoreState())
    val state = _state.asStateFlow()

    private val _events = Channel<RegisterEvent>()
    val events = _events.receiveAsFlow()

    private var cooldownJob: Job? = null

    init {
        val restored = _state.value
        if (restored.step == RegisterStep.EnterCode && restored.resendInSeconds > 0) {
            startCooldown(restored.resendInSeconds)
        }
    }

    fun onAction(action: RegisterAction) {
        when (action) {
            is RegisterAction.OnEmailChange -> {
                savedStateHandle[KEY_EMAIL] = action.email
                _state.update { it.copy(email = action.email, emailError = null) }
            }
            is RegisterAction.OnParticipantChange -> {
                savedStateHandle[KEY_PARTICIPANT] = action.participant
                _state.update { it.copy(participant = action.participant, participantError = null) }
            }
            is RegisterAction.OnCodeChange ->
                _state.update { it.copy(code = action.code, codeError = null, error = null) }
            RegisterAction.OnSendCodeClick -> sendCode(isResend = false)
            RegisterAction.OnResendClick -> sendCode(isResend = true)
            RegisterAction.OnVerifyClick -> verify()
            RegisterAction.OnBackToDetails -> {
                savedStateHandle[KEY_STEP] = RegisterStep.EnterDetails.name
                _state.update {
                    it.copy(step = RegisterStep.EnterDetails, code = "", codeError = null, error = null)
                }
            }
            RegisterAction.OnErrorDismiss -> _state.update { it.copy(error = null) }
        }
    }

    private fun sendCode(isResend: Boolean) {
        if (_state.value.isLoading) return
        if (isResend && !_state.value.canResend) return

        val email = _state.value.email
        val participant = _state.value.participant

        val emailValid = validateEmail(email)
        val participantValid = validateParticipant(participant)
        if (emailValid is Result.Error || participantValid is Result.Error) {
            _state.update {
                it.copy(
                    emailError = (emailValid as? Result.Error)?.error?.toUiText(),
                    participantError = (participantValid as? Result.Error)?.error?.toUiText(),
                )
            }
            return
        }

        viewModelScope.launch {
            _state.update {
                it.copy(isLoading = true, error = null, emailError = null, participantError = null)
            }
            when (val result = authRepository.sendRegistrationCode(email, participant)) {
                is Result.Success -> {
                    savedStateHandle[KEY_STEP] = RegisterStep.EnterCode.name
                    _state.update {
                        it.copy(
                            isLoading = false,
                            step = RegisterStep.EnterCode,
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
            when (val result = authRepository.verifyRegistrationCode(_state.value.email, code)) {
                is Result.Success -> {
                    _state.update { it.copy(isLoading = false) }
                    _events.send(RegisterEvent.NavigateToHome)
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

    private fun restoreState(): RegisterState {
        val step = savedStateHandle.get<String>(KEY_STEP)
            ?.let { runCatching { RegisterStep.valueOf(it) }.getOrNull() }
            ?: RegisterStep.EnterDetails
        val remaining = savedStateHandle.get<Int>(KEY_RESEND) ?: 0
        return RegisterState(
            step = step,
            email = savedStateHandle[KEY_EMAIL] ?: "",
            participant = savedStateHandle[KEY_PARTICIPANT] ?: "",
            resendInSeconds = remaining,
            canResend = remaining == 0,
        )
    }

    private companion object {
        const val KEY_STEP = "register_step"
        const val KEY_EMAIL = "register_email"
        const val KEY_PARTICIPANT = "register_participant"
        const val KEY_RESEND = "register_resend_in"
    }
}
