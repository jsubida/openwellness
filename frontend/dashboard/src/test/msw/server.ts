// MSW node server seeded with the happy-path handlers. The lifecycle
// (listen/resetHandlers/close) is wired PER TEST FILE — never in the global
// test setup — so the 135 existing fetch-stubbing suites are untouched.
import { setupServer } from 'msw/node'

import { defaultHandlers } from './handlers'

export const server = setupServer(...defaultHandlers)
