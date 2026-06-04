package edu.openwellness.mobile.feature.auth.presentation.login

import androidx.lifecycle.SavedStateHandle
import app.cash.turbine.test
import assertk.assertThat
import assertk.assertions.isEqualTo
import assertk.assertions.isFalse
import assertk.assertions.isNotNull
import assertk.assertions.isTrue
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError
import edu.openwellness.mobile.feature.auth.domain.model.SendCodeResult
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateEmail
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateOtpCode
import edu.openwellness.mobile.feature.auth.presentation.FakeAuthRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test

private const val VALID_EMAIL = "person@example.com"
private const val VALID_CODE = "123456"

class LoginViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var repo: FakeAuthRepository

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        repo = FakeAuthRepository()
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun viewModel() =
        LoginViewModel(repo, ValidateEmail(), ValidateOtpCode(), SavedStateHandle())

    @Test
    fun sendSuccess_advancesToCodeStep() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)

        assertThat(vm.state.value.step).isEqualTo(LoginStep.EnterCode)
        assertThat(repo.sendCallCount).isEqualTo(1)
    }

    @Test
    fun unknownEmail_stillAdvances_antiEnumeration() = runTest(testDispatcher) {
        repo.sendResult = Result.Success(SendCodeResult(900, 60, "uniform"))
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange("nobody@nowhere.test"))
        vm.onAction(LoginAction.OnSendCodeClick)

        assertThat(vm.state.value.step).isEqualTo(LoginStep.EnterCode)
    }

    @Test
    fun invalidEmail_blocksSend() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange("not-an-email"))
        vm.onAction(LoginAction.OnSendCodeClick)

        assertThat(vm.state.value.emailError).isNotNull()
        assertThat(vm.state.value.step).isEqualTo(LoginStep.EnterEmail)
        assertThat(repo.sendCallCount).isEqualTo(0)
    }

    @Test
    fun sendStartsCooldown_thatElapsesWithVirtualTime() = runTest(testDispatcher) {
        repo.sendResult = Result.Success(SendCodeResult(900, 60, "ok"))
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)

        assertThat(vm.state.value.resendInSeconds).isEqualTo(60)
        assertThat(vm.state.value.canResend).isFalse()

        advanceUntilIdle()

        assertThat(vm.state.value.resendInSeconds).isEqualTo(0)
        assertThat(vm.state.value.canResend).isTrue()
    }

    @Test
    fun verifySuccess_emitsNavigateToHome() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)
        vm.onAction(LoginAction.OnCodeChange(VALID_CODE))

        vm.events.test {
            vm.onAction(LoginAction.OnVerifyClick)
            assertThat(awaitItem()).isEqualTo(LoginEvent.NavigateToHome)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun invalidOrExpiredCode_showsUniformError_andStaysOnCodeStep() = runTest(testDispatcher) {
        repo.verifyResult = Result.Error(AuthError.InvalidOrExpiredCode)
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)
        vm.onAction(LoginAction.OnCodeChange(VALID_CODE))
        vm.onAction(LoginAction.OnVerifyClick)

        assertThat(vm.state.value.error).isNotNull()
        assertThat(vm.state.value.step).isEqualTo(LoginStep.EnterCode)
    }

    @Test
    fun rateLimitedVerify_setsCooldownToServerValue() = runTest(testDispatcher) {
        repo.sendResult = Result.Success(SendCodeResult(900, 0, "ok"))
        repo.verifyResult = Result.Error(AuthError.RateLimited(42))
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)
        vm.onAction(LoginAction.OnCodeChange(VALID_CODE))
        vm.onAction(LoginAction.OnVerifyClick)

        assertThat(vm.state.value.resendInSeconds).isEqualTo(42)
        assertThat(vm.state.value.canResend).isFalse()
        assertThat(vm.state.value.error).isNotNull()
    }

    @Test
    fun resend_isIgnoredWhileCooldownActive() = runTest(testDispatcher) {
        repo.sendResult = Result.Success(SendCodeResult(900, 60, "ok"))
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)
        assertThat(repo.sendCallCount).isEqualTo(1)
        assertThat(vm.state.value.canResend).isFalse()

        vm.onAction(LoginAction.OnResendClick)

        assertThat(repo.sendCallCount).isEqualTo(1)
    }

    @Test
    fun invalidCodeFormat_blocksVerify() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(LoginAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(LoginAction.OnSendCodeClick)
        vm.onAction(LoginAction.OnCodeChange("12")) // too short

        vm.onAction(LoginAction.OnVerifyClick)

        assertThat(vm.state.value.codeError).isNotNull()
        assertThat(repo.verifyCallCount).isEqualTo(0)
    }
}
