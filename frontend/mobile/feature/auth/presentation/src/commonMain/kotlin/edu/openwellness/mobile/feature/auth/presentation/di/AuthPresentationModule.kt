package edu.openwellness.mobile.feature.auth.presentation.di

import edu.openwellness.mobile.feature.auth.presentation.login.LoginViewModel
import edu.openwellness.mobile.feature.auth.presentation.register.RegisterViewModel
import org.koin.core.module.dsl.viewModelOf
import org.koin.dsl.module

/** ViewModels resolve their use cases + repository from the data/core modules. */
val authPresentationModule = module {
    viewModelOf(::LoginViewModel)
    viewModelOf(::RegisterViewModel)
}
