const models = ["gpt-4o-mini", "claude-3-haiku", "gemini-2.0-flash-exp"];

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

async function getModelAccuracy(model) {
  const correctUrl = `../results/correct_solutions_${model}.json`;
  const resultsUrl = `../results/results_${model}.json`;

  try {
    const [correctData, resultsData] = await Promise.all([
      fetchJSON(correctUrl),
      fetchJSON(resultsUrl),
    ]);

    const correctCount = Object.keys(correctData).length;
    const totalCount = Object.keys(resultsData).length;

    return { model, correctCount, totalCount };
  } catch (e) {
    console.error(e);
    return { model, correctCount: 0, totalCount: 0, error: true };
  }
}

function createTableRow({ model, correctCount, totalCount, error }) {
  if (error) {
    return `
      <tr>
        <td>${model}</td>
        <td colspan="1" class="text-danger">What the helly 'Bron James?</td>
      </tr>
    `;
  }
  const accuracy = totalCount > 0 ? `${correctCount} / ${totalCount}` : "No data";
  return `
    <tr>
      <td>${model}</td>
      <td>${accuracy}</td>
    </tr>
  `;
}

async function displayResults() {
  const container = document.getElementById("resultsContainer");

  let html = `
    <table class="table table-striped">
      <thead>
        <tr><th>Model</th><th>Accuracy (correct / total)</th></tr>
      </thead>
      <tbody>
  `;

  for (const model of models) {
    const stats = await getModelAccuracy(model);
    html += createTableRow(stats);
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

displayResults();