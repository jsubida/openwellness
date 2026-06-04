package edu.openwellness.mobile.feature.auth.data.di

import edu.openwellness.mobile.feature.auth.data.KtorAuthRemoteDataSource
import edu.openwellness.mobile.feature.auth.data.OpenWellnessAuthRepository
import edu.openwellness.mobile.feature.auth.domain.AuthRepository
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateEmail
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateOtpCode
import edu.openwellness.mobile.feature.auth.domain.usecase.ValidateParticipant
import org.koin.dsl.module

val authDataModule = module {
    single { KtorAuthRemoteDataSource(get(), get()) }
    single<AuthRepository> { OpenWellnessAuthRepository(get(), get(), get()) }

    factory { ValidateEmail() }
    factory { ValidateOtpCode() }
    factory { ValidateParticipant() }
}
