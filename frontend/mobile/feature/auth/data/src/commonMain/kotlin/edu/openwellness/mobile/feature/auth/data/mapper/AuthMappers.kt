package edu.openwellness.mobile.feature.auth.data.mapper

import edu.openwellness.mobile.feature.auth.data.dto.PrincipalDto
import edu.openwellness.mobile.feature.auth.data.dto.TokenResponseDto
import edu.openwellness.mobile.feature.auth.data.dto.UniformSendResponseDto
import edu.openwellness.mobile.feature.auth.domain.model.AuthSession
import edu.openwellness.mobile.feature.auth.domain.model.AuthTokens
import edu.openwellness.mobile.feature.auth.domain.model.Principal
import edu.openwellness.mobile.feature.auth.domain.model.SendCodeResult

fun UniformSendResponseDto.toSendCodeResult(): SendCodeResult = SendCodeResult(
    expiresInSeconds = expiresInSeconds,
    resendAfterSeconds = resendAfterSeconds,
    message = message,
)

fun PrincipalDto.toPrincipal(): Principal = Principal(
    userId = userId,
    participant = participant,
)

fun TokenResponseDto.toAuthSession(): AuthSession = AuthSession(
    tokens = AuthTokens(
        accessToken = accessToken,
        refreshToken = refreshToken,
        tokenType = tokenType,
        expiresInSeconds = expiresInSeconds,
    ),
    principal = principal.toPrincipal(),
)
