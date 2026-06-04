package edu.openwellness.mobile.feature.auth.presentation.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import edu.openwellness.mobile.core.presentation.components.EmailTextField
import edu.openwellness.mobile.core.presentation.components.ErrorText
import edu.openwellness.mobile.core.presentation.components.LoadingButton
import edu.openwellness.mobile.core.presentation.components.OtpInputField
import edu.openwellness.mobile.core.presentation.theme.OpenWellnessTheme
import edu.openwellness.mobile.core.presentation.util.ObserveAsEvents
import edu.openwellness.mobile.feature.auth.presentation.resources.Res
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_change_email
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_code_sent
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_email_label
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_login_title
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_otp_cd
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_resend
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_resend_in
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_send_code
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_verify
import org.jetbrains.compose.resources.stringResource
import org.koin.compose.viewmodel.koinViewModel

@Composable
fun LoginRoot(
    onNavigateToHome: () -> Unit,
    viewModel: LoginViewModel = koinViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    ObserveAsEvents(viewModel.events) { event ->
        when (event) {
            LoginEvent.NavigateToHome -> onNavigateToHome()
        }
    }

    LoginScreen(state = state, onAction = viewModel::onAction)
}

@Composable
fun LoginScreen(
    state: LoginState,
    onAction: (LoginAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .safeContentPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = stringResource(Res.string.auth_login_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        when (state.step) {
            LoginStep.EnterEmail -> EmailStep(state, onAction)
            LoginStep.EnterCode -> CodeStep(state, onAction)
        }
    }
}

@Composable
private fun ColumnScope.EmailStep(
    state: LoginState,
    onAction: (LoginAction) -> Unit,
) {
    EmailTextField(
        value = state.email,
        onValueChange = { onAction(LoginAction.OnEmailChange(it)) },
        label = stringResource(Res.string.auth_email_label),
        isError = state.emailError != null,
        errorText = state.emailError?.asString(),
        enabled = !state.isLoading,
        imeAction = ImeAction.Done,
        onImeAction = { onAction(LoginAction.OnSendCodeClick) },
    )
    state.error?.let { ErrorText(text = it.asString()) }
    LoadingButton(
        text = stringResource(Res.string.auth_send_code),
        isLoading = state.isLoading,
        onClick = { onAction(LoginAction.OnSendCodeClick) },
        enabled = state.resendInSeconds == 0,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun ColumnScope.CodeStep(
    state: LoginState,
    onAction: (LoginAction) -> Unit,
) {
    Text(
        text = stringResource(Res.string.auth_code_sent, state.email),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OtpInputField(
        code = state.code,
        onCodeChange = { onAction(LoginAction.OnCodeChange(it)) },
        contentDescription = stringResource(Res.string.auth_otp_cd),
        isError = state.error != null || state.codeError != null,
        enabled = !state.isLoading,
        onFilled = { onAction(LoginAction.OnVerifyClick) },
    )
    state.codeError?.let { ErrorText(text = it.asString()) }
    state.error?.let { ErrorText(text = it.asString()) }
    LoadingButton(
        text = stringResource(Res.string.auth_verify),
        isLoading = state.isLoading,
        onClick = { onAction(LoginAction.OnVerifyClick) },
        enabled = state.code.length == OTP_LENGTH,
        modifier = Modifier.fillMaxWidth(),
    )
    if (state.canResend) {
        TextButton(
            onClick = { onAction(LoginAction.OnResendClick) },
            enabled = !state.isLoading,
        ) {
            Text(stringResource(Res.string.auth_resend))
        }
    } else {
        Text(
            text = stringResource(Res.string.auth_resend_in, state.resendInSeconds),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    TextButton(
        onClick = { onAction(LoginAction.OnBackToEmail) },
        enabled = !state.isLoading,
    ) {
        Text(stringResource(Res.string.auth_change_email))
    }
}

private const val OTP_LENGTH = 6

@Preview
@Composable
private fun LoginEmailStepPreview() {
    OpenWellnessTheme {
        LoginScreen(state = LoginState(email = "person@example.com"), onAction = {})
    }
}

@Preview
@Composable
private fun LoginCodeStepPreview() {
    OpenWellnessTheme {
        LoginScreen(
            state = LoginState(
                step = LoginStep.EnterCode,
                email = "person@example.com",
                code = "123",
                resendInSeconds = 42,
            ),
            onAction = {},
        )
    }
}
