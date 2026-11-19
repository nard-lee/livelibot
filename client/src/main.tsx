import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { guestRoute } from './layouts/GuestLayout'
import { authRoute } from './layouts/AuthLayout'
import { homeRoute } from './guest/home'
import { loginRoute } from './features/auth/Login'
import { signupRoute } from './features/auth/Signup'
import { chatRoute } from './features/chat/Chat'
import { documentsRoute } from './features/documents/Documents'

const router = createBrowserRouter([
  {
    ...guestRoute,
    children: [homeRoute, loginRoute, signupRoute],
  },
  {
    ...authRoute,
    children: [chatRoute, documentsRoute],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router}/>
  </StrictMode>,
)
