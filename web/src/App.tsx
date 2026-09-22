import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/ui'
import HomePage from './pages/HomePage'
import MapPage from './pages/MapPage'
import AirportPage from './pages/AirportPage'
import FlightPage from './pages/FlightPage'
import AboutPage from './pages/AboutPage'

const client = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60 * 1000, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/airport/:ident" element={<AirportPage />} />
            <Route path="/flight" element={<FlightPage />} />
            <Route path="/about" element={<AboutPage />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
