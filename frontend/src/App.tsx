// Presentation layer shell. The ask form, answer card, citations and security panel
// are added on top of the answers API in a later commit.
export function App() {
  return (
    <main className="app">
      <header>
        <h1>Legislation Q&amp;A</h1>
        <p className="tagline">
          Evidence excerpts from Australian legislation, with verified citations. Not legal advice.
        </p>
      </header>
    </main>
  );
}
