import { createContext, useContext, type ReactNode } from "react"

interface GuestShareContextType {
  isGuest: boolean
  guestShareId: string | null
  agentId: string | null
  guestShareToken: string | null
}

const GuestShareContext = createContext<GuestShareContextType>({
  isGuest: false,
  guestShareId: null,
  agentId: null,
  guestShareToken: null,
})

interface GuestShareProviderProps {
  children: ReactNode
  guestShareId: string | null
  agentId: string | null
  guestShareToken: string | null
}

export function GuestShareProvider({
  children,
  guestShareId,
  agentId,
  guestShareToken,
}: GuestShareProviderProps) {
  return (
    <GuestShareContext.Provider
      value={{
        isGuest: true,
        guestShareId,
        agentId,
        guestShareToken,
      }}
    >
      {children}
    </GuestShareContext.Provider>
  )
}

export function useGuestShare() {
  return useContext(GuestShareContext)
}

export default useGuestShare
