package edu.openwellness.mobile.feature.auth.presentation.register

import androidx.lifecycle.SavedStateHandle
import app.cash.turbine.test
import assertk.assertThat
import assertk.assertions.isEqualTo
import assertk.assertions.isNotNull
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.model.SendCodeResult
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateEmail
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateOtpCode
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateParticipant
import edu.openwellness.mobile.feature.auth.presentation.FakeAuthRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test

private const val VALID_EMAIL = "person@example.com"
private const val VALID_PARTICIPANT = "participants/42"
private const val VALID_CODE = "123456"

class RegisterViewModelTest {

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

    private fun viewModel() = RegisterViewModel(
        repo,
        ValidateEmail(),
        ValidateParticipant(),
        ValidateOtpCode(),
        SavedStateHandle(),
    )

    @Test
    fun sendSuccess_advancesAndForwardsParticipant() = runTest(testDispatcher) {
        repo.sendResult = Result.Success(SendCodeResult(900, 60, "ok"))
        val vm = viewModel()
        vm.onAction(RegisterAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(RegisterAction.OnParticipantChange(VALID_PARTICIPANT))
        vm.onAction(RegisterAction.OnSendCodeClick)

        assertThat(vm.state.value.step).isEqualTo(RegisterStep.EnterCode)
        assertThat(repo.sendCallCount).isEqualTo(1)
        assertThat(repo.lastSendParticipant).isEqualTo(VALID_PARTICIPANT)
    }

    @Test
    fun emptyParticipant_blocksSend() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(RegisterAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(RegisterAction.OnParticipantChange("   "))
        vm.onAction(RegisterAction.OnSendCodeClick)

        assertThat(vm.state.value.participantError).isNotNull()
        assertThat(vm.state.value.step).isEqualTo(RegisterStep.EnterDetails)
        assertThat(repo.sendCallCount).isEqualTo(0)
    }

    @Test
    fun invalidEmailAndParticipant_bothReported() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(RegisterAction.OnEmailChange("bad"))
        vm.onAction(RegisterAction.OnParticipantChange(""))
        vm.onAction(RegisterAction.OnSendCodeClick)

        assertThat(vm.state.value.emailError).isNotNull()
        assertThat(vm.state.value.participantError).isNotNull()
        assertThat(repo.sendCallCount).isEqualTo(0)
    }

    @Test
    fun verifySuccess_emitsNavigateToHome() = runTest(testDispatcher) {
        val vm = viewModel()
        vm.onAction(RegisterAction.OnEmailChange(VALID_EMAIL))
        vm.onAction(RegisterAction.OnParticipantChange(VALID_PARTICIPANT))
        vm.onAction(RegisterAction.OnSendCodeClick)
        vm.onAction(RegisterAction.OnCodeChange(VALID_CODE))

        vm.events.test {
            vm.onAction(RegisterAction.OnVerifyClick)
            assertThat(awaitItem()).isEqualTo(RegisterEvent.NavigateToHome)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
