// App shell: global providers wrapping the router. The route table and the
// auth/query providers live in their own modules (router.tsx, providers.tsx).
import { RouterProvider } from 'react-router-dom'

import { Providers } from './providers'
import { router } from './router'

export default function App() {
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  )
}
