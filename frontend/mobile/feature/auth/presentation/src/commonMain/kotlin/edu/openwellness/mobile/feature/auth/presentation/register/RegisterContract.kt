package edu.openwellness.mobile.feature.auth.presentation.register

import edu.openwellness.mobile.core.presentation.util.UiText

enum class RegisterStep { EnterDetails, EnterCode }

data class RegisterState(
    val step: RegisterStep = RegisterStep.EnterDetails,
    val email: String = "",
    val participant: String = "",
    val code: String = "",
    val isLoading: Boolean = false,
    val error: UiText? = null,
    val emailError: UiText? = null,
    val participantError: UiText? = null,
    val codeError: UiText? = null,
    val resendInSeconds: Int = 0,
    val canResend: Boolean = false,
)

sealed interface RegisterAction {
    data class OnEmailChange(val email: String) : RegisterAction
    data class OnParticipantChange(val participant: String) : RegisterAction
    data class OnCodeChange(val code: String) : RegisterAction
    data object OnSendCodeClick : RegisterAction
    data object OnVerifyClick : RegisterAction
    data object OnResendClick : RegisterAction
    data object OnBackToDetails : RegisterAction
    data object OnErrorDismiss : RegisterAction
}

sealed interface RegisterEvent {
    data object NavigateToHome : RegisterEvent
}
