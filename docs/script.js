const models = ["gpt-4o-mini", "claude-3-haiku-20240307", "gemini-2.0-flash-exp", "o4-mini-2025-04-16", "claude-3-opus-20240229", "gemini-1.5-pro"];

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

/*
For now:
Very easy: solvers >= 1000
Easy: 600-999 solvers
Medium: 100-599 solvers
Hard: 30 - 100 > solvers.
Very hard: 0-29 solvers
*/
function classifyDifficulty(numSolvers) {
  if (numSolvers >= 1000) return "Very Easy";
  if (numSolvers >= 600) return "Easy";
  if (numSolvers >= 100) return "Medium";
  if (numSolvers >= 30) return "Hard";
  return "Very Hard";
}
async function getTotalPuzzlesPerDifficulty() {
  return new Promise((resolve, reject) => {
    Papa.parse("data/puzzles.csv", {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const difficultyCounts = {
          "Very Easy": 0,
          "Easy": 0,
          "Medium": 0,
          "Hard": 0,
          "Very Hard": 0
        };

        results.data.forEach(row => {
          const numSolvers = parseInt(row.numSolvers);
          if (!isNaN(numSolvers)) {
            const diff = classifyDifficulty(numSolvers);
            difficultyCounts[diff]++;
          }
        });

        resolve(difficultyCounts);
      },
      error: (err) => reject(err)
    });
  });
}

async function getModelAccuracy(model, totalByDifficulty) {
  const correctUrl = `results/full_correct_${model}.json`;
  const partialCorrectUrl = `results/partial_correct_${model}.json`;
  const resultsUrl = `results/results_${model}.json`;

  // Helper to fetch and return {} if file doesn't exist
  async function safeFetchJSON(url) {
    try {
      return await fetchJSON(url);
    } catch (e) {
      if (e.message.includes('404') || e.message.includes('not found')) {
        return {};
      }
      throw e;
    }
  }

  try {
    const [correctData, partialCorrectData, resultsData] = await Promise.all([
      safeFetchJSON(correctUrl),
      safeFetchJSON(partialCorrectUrl),
      fetchJSON(resultsUrl),
    ]);

    const correctCount = Object.keys(correctData).length;
    const partialCorrectCount = Object.keys(partialCorrectData).length;
    const totalCount = Object.keys(resultsData).length;

    const percentCorrect = totalCount > 0 ? ((correctCount / totalCount) * 100).toFixed(2) : 0;
    const percentPartialCorrect = totalCount > 0 ? ((partialCorrectCount / totalCount) * 100).toFixed(2) : 0;

    const difficultyCounts = {
      "Very Easy": 0,
      "Easy": 0,
      "Medium": 0,
      "Hard": 0,
      "Very Hard": 0
    };

    for (const problemId in correctData) {
      const problem = correctData[problemId];
      const diff = classifyDifficulty(problem.numSolvers);
      difficultyCounts[diff]++;
    }

    const difficultyBreakdown = {};
    for (const diff in difficultyCounts) {
      const solved = difficultyCounts[diff];
      const total = totalByDifficulty[diff] || 0;
      difficultyBreakdown[diff] = `${solved} / ${total}`;
    }

    return {
      model,
      correctCount,
      partialCorrectCount,
      totalCount,
      percentCorrect,
      percentPartialCorrect,
      difficultyCounts: difficultyBreakdown,
      correctData,
      partialCorrectData
    };
  } catch (e) {
    console.error(e);
    return { model, correctCount: 0, partialCorrectCount: 0, totalCount: 0, percentCorrect: 0, percentPartialCorrect: 0, error: true };
  }
}

function createTableRow(rank, data) {
  const {
    model,
    correctCount,
    partialCorrectCount,
    totalCount,
    percentCorrect,
    percentPartialCorrect,
    error,
    difficultyCounts,
    correctData = {},
    partialCorrectData = {}
  } = data;
  if (error) {
    return `
      <tr>
        <td>${model}</td>
        <td colspan="1" class="text-danger">Not available yet</td>
      </tr>
    `;
  }

  console.log(correctData);

  const collapseId = `collapse-${rank}`;
  const correctList = Object.values(correctData)
  .map(puzzle => `<code>${puzzle.name}</code>`)
  .join(', ') || "<em>None</em>";

  const partialList = Object.values(partialCorrectData)
    .map(puzzle => `<code>${puzzle.name}</code>`)
    .join(', ') || "<em>None</em>";

  return `
    <tr data-bs-toggle="collapse" data-bs-target="#${collapseId}" style="cursor: pointer;">
      <td>${rank}</td>
      <td>${model}</td>
      <td>${correctCount} (${percentCorrect}%)</td>
      <td>${partialCorrectCount} (${percentPartialCorrect}%)</td>
      <td>${difficultyCounts["Very Easy"]}</td>
      <td>${difficultyCounts["Easy"]}</td>
      <td>${difficultyCounts["Medium"]}</td>
      <td>${difficultyCounts["Hard"]}</td>
      <td>${difficultyCounts["Very Hard"]}</td>
      <td>${totalCount}</td>
    </tr>
    <tr class="collapse" id="${collapseId}">
      <td colspan="10" class="bg-light">
        <strong>Correct:</strong> ${correctList}<br>
        <strong>Partially Correct:</strong> ${partialList}
      </td>
    </tr>
  `;
}

async function displayResults() {
  const container = document.getElementById("resultsContainer");
  const totalByDifficulty = await getTotalPuzzlesPerDifficulty();

  let statsArray = [];
  for (const model of models) {
    const stats = await getModelAccuracy(model, totalByDifficulty);
    statsArray.push(stats);
  }

  // Sort by accuracy (descending)
  statsArray.sort((a, b) => {
    const accA = a.totalCount > 0 ? a.correctCount / a.totalCount : 0;
    const accB = b.totalCount > 0 ? b.correctCount / b.totalCount : 0;
    return accB - accA;
  });

  let html = `
    <table class="table table-striped">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Model</th>
          <th># Correct</th>
          <th># Partially Correct</th>
          <th>Very Easy</th>
          <th>Easy</th>
          <th>Medium</th>
          <th>Hard</th>
          <th>Very Hard</th>
          <th>Total puzzles</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (let i = 0; i < statsArray.length; i++) {
    html += createTableRow(i+1, statsArray[i]);
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

displayResults();