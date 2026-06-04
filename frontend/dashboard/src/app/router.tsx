// Route table. `/` is the public landing+login page (must stay public — see
// RequireAuth's redirect contract); `/home` is guarded by the RequireAuth
// layout route; anything else redirects back to the landing page.
import { createBrowserRouter, Navigate } from 'react-router-dom'

import { RequireAuth } from '@/core/auth/RequireAuth'
import { LandingLoginPage } from '@/features/auth/ui/LandingLoginPage'
import { HomePage } from '@/pages/HomePage'

import { ROUTES } from './routes'

export const router = createBrowserRouter([
  {
    path: ROUTES.landing,
    element: <LandingLoginPage />,
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: ROUTES.home,
        element: <HomePage />,
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to={ROUTES.landing} replace />,
  },
])
