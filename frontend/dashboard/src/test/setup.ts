import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// RTL only auto-registers cleanup when Vitest globals are enabled; we keep
// globals off (explicit imports), so register it ourselves.
afterEach(cleanup)
