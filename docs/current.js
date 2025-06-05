const models = ["gpt-4o-mini", "claude-3-haiku-20240307", "gemini-2.0-flash-exp", "o4-mini-2025-04-16", "claude-3-opus-20240229", "gemini-1.5-pro"];

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

async function getCurrentPuzzleOutputs() {
  const container = document.getElementById("currentPuzzleContainer");

  let puzzleName = "";
  const rows = [];

  for (const model of models) {
    try {
      const results = await fetchJSON(`results/results_${model}.json`);
      const firstPuzzle = results["0"];

      if (!firstPuzzle) throw new Error(`No puzzle 0 for model ${model}`);

      if (!puzzleName) puzzleName = firstPuzzle.name;

      const firstAnswer = firstPuzzle.answers?.[0]?.answer || "No answer found";
      const secondAnswer = firstPuzzle.answers?.[1]?.answer || "No answer found";

      rows.push(`
        <tr>
          <td>${model}</td>
          <td><pre>${firstAnswer}</pre></td>
          <td><pre>${secondAnswer}</pre></td>
        </tr>
      `);
    } catch (e) {
      console.error(e);
      rows.push(`
        <tr>
          <td>${model}</td>
          <td class="text-danger">Not available yet</td>
        </tr>
      `);
    }
  }

  container.innerHTML = `
    <h2>Puzzle: ${puzzleName || "Unknown"}</h2>
    <table class="table table-striped">
      <thead>
        <tr>
          <th>Model</th>
          <th>First Attempt</th>
          <th>Second Attempt</th>
        </tr>
      </thead>
      <tbody>
        ${rows.join("\n")}
      </tbody>
    </table>
  `;
}

getCurrentPuzzleOutputs();