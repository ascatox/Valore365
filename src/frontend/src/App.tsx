import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/clerk-react";
import Dashboard from "./pages/Dashboard";
 
function App() {
  return (
    <header>
      <SignedOut>
        <SignInButton />
      </SignedOut>
      <SignedIn>
        <UserButton />
        <Dashboard />
      </SignedIn>
    </header>
  )
}
 
export default App
