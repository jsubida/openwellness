package edu.openwellness.mobile.feature.auth.presentation.login

import edu.openwellness.mobile.core.presentation.util.UiText

enum class LoginStep { EnterEmail, EnterCode }

data class LoginState(
    val step: LoginStep = LoginStep.EnterEmail,
    val email: String = "",
    val code: String = "",
    val isLoading: Boolean = false,
    val error: UiText? = null,
    val emailError: UiText? = null,
    val codeError: UiText? = null,
    val resendInSeconds: Int = 0,
    val canResend: Boolean = false,
)

sealed interface LoginAction {
    data class OnEmailChange(val email: String) : LoginAction
    data class OnCodeChange(val code: String) : LoginAction
    data object OnSendCodeClick : LoginAction
    data object OnVerifyClick : LoginAction
    data object OnResendClick : LoginAction
    data object OnBackToEmail : LoginAction
    data object OnErrorDismiss : LoginAction
}

sealed interface LoginEvent {
    data object NavigateToHome : LoginEvent
}
