package edu.openwellness.mobile.feature.auth.domain.usecase

import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidateEmailTest {
    private val validate = ValidateEmail()

    @Test
    fun acceptsAWellFormedEmail() {
        assertTrue(validate("person@example.com") is Result.Success)
    }

    @Test
    fun trimsSurroundingWhitespace() {
        assertTrue(validate("  person@example.com  ") is Result.Success)
    }

    @Test
    fun rejectsMissingAtSign() {
        val result = validate("personexample.com")
        assertTrue(result is Result.Error)
        assertEquals(AuthError.InvalidEmail, result.error)
    }

    @Test
    fun rejectsBlank() {
        assertTrue(validate("   ") is Result.Error)
    }
}

class ValidateOtpCodeTest {
    private val validate = ValidateOtpCode()

    @Test
    fun acceptsExactlySixDigits() {
        assertTrue(validate("123456") is Result.Success)
    }

    @Test
    fun rejectsFewerThanSixDigits() {
        assertTrue(validate("12345") is Result.Error)
    }

    @Test
    fun rejectsNonDigits() {
        val result = validate("12a456")
        assertTrue(result is Result.Error)
        assertEquals(AuthError.InvalidCode, result.error)
    }

    @Test
    fun rejectsMoreThanSixDigits() {
        assertTrue(validate("1234567") is Result.Error)
    }
}

class ValidateParticipantTest {
    private val validate = ValidateParticipant()

    @Test
    fun acceptsABareId() {
        assertTrue(validate("42") is Result.Success)
    }

    @Test
    fun acceptsAResourceName() {
        assertTrue(validate("participants/42") is Result.Success)
    }

    @Test
    fun rejectsBlank() {
        val result = validate("   ")
        assertTrue(result is Result.Error)
        assertEquals(AuthError.EmptyParticipant, result.error)
    }

    @Test
    fun rejectsAPrefixWithNothingAfterIt() {
        assertTrue(validate("participants/") is Result.Error)
    }
}
