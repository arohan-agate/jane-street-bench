const models = [
  "gpt-4o-mini",
  "gpt-4o-2024-08-06",
  "gpt-4.1-2025-04-14",
  "o3-2025-04-16",
  "o4-mini-2025-04-16",
  "gemini-1.5-pro",
  "gemini-2.0-flash-exp",
  "claude-3-haiku-20240307",
  "claude-3-opus-20240229",
];


async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

/*
 Now “Medium” = ≥100 solvers,
      “Hard”   = 30–99 solvers,
      “Very Hard” = <30 solvers.
*/
function classifyDifficulty(numSolvers) {
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

async function getModelAccuracy(model, totalByDifficulty, categoryMap) {
  const correctUrl = `results/full_correct_${model}.json`;
  const partialCorrectUrl = `results/partial_correct_${model}.json`;
  const resultsUrl = `results/results_${model}.json`;

  async function safeFetchJSON(url) {
    try {
      return await fetchJSON(url);
    } 
    catch (e) {
      if (e.message.includes("404") || e.message.includes("not found")) {
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

    const percentCorrect = totalCount > 0
      ? ((correctCount / totalCount) * 100).toFixed(2)
      : 0;
    const percentPartialCorrect = totalCount > 0
      ? ((partialCorrectCount / totalCount) * 100).toFixed(2)
      : 0;

    const difficultyCounts = {
      "Medium": 0,
      "Hard": 0,
      "Very Hard": 0
    };

    const categoryCounts = {
      math: 0,
      probability: 0,
      geometry: 0,
      logic_puzzle: 0,
      image_only: 0,
      text_only: 0,
      mixed_input: 0,
      language: 0,
      abstract: 0
    };

    for (const problemId in correctData) {
      const problem = correctData[problemId];
      const diff = classifyDifficulty(problem.numSolvers);
      difficultyCounts[diff]++;

      const cat = categoryMap[problemId];
      if (cat) {
        for (const key in categoryCounts) {
          if (cat[key] === "1") categoryCounts[key]++;
        }
      }
    }

    const breakdown = {};
    const totalPuzzles = Object.values(totalByDifficulty).reduce((a, b) => a + b, 0);
    const unattempted = totalPuzzles - totalCount;

    breakdown["Medium"]    = `${difficultyCounts["Medium"]} / ${totalByDifficulty["Medium"] || 0}`;
    breakdown["Hard"]      = `${difficultyCounts["Hard"]} / ${totalByDifficulty["Hard"] || 0}`;
    breakdown["Very Hard"] = `${difficultyCounts["Very Hard"]} / ${totalByDifficulty["Very Hard"] || 0}`;
    breakdown["Unattempted"] = `${unattempted}`;

    return {
      model,
      correctCount,
      partialCorrectCount,
      totalCount,
      percentCorrect,
      percentPartialCorrect,
      difficultyCounts: breakdown,
      categoryCounts,
      correctData,
      partialCorrectData
    };
  } catch (e) {
    console.error(e);
    return {
      model,
      correctCount: 0,
      partialCorrectCount: 0,
      totalCount: 0,
      percentCorrect: 0,
      percentPartialCorrect: 0,
      difficultyCounts: {
        "Medium": `0 / ${totalByDifficulty["Medium"] || 0}`,
        "Hard": `0 / ${totalByDifficulty["Hard"] || 0}`,
        "Very Hard": `0 / ${totalByDifficulty["Very Hard"] || 0}`,
        "Unattempted": `${(totalByDifficulty["Medium"]||0)+(totalByDifficulty["Hard"]||0)+(totalByDifficulty["Very Hard"]||0)}`
      },
      categoryCounts: {
        math: 0, probability: 0, geometry: 0, logic_puzzle: 0,
        image_only: 0, text_only: 0, mixed_input: 0, language: 0, abstract: 0
      },
      correctData: {},
      partialCorrectData: {},
      error: true
    };
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
    difficultyCounts = {},
    categoryCounts = {},
    correctData = {},
    partialCorrectData = {}
  } = data;

  if (error) {
    return `
      <tr>
        <td colspan="18" class="text-danger">Model ${model} not available yet</td>
      </tr>
    `;
  }

  const collapseId = `collapse-${rank}`;
  const correctList = Object.values(correctData).map(p => `<code>${p.name}</code>`).join(", ") || "<em>None</em>";
  const partialList = Object.values(partialCorrectData).map(p => `<code>${p.name}</code>`).join(", ") || "<em>None</em>";

  const displayModelName = model.replace(/-(\d{4}-\d{2}-\d{2}|\d{8})$/, "").replace(/-\d{8}$/, "");

  const summaryRow = `
    <tr data-bs-toggle="collapse" data-bs-target="#${collapseId}" style="cursor: pointer;">
      <td>${rank}</td>
      <td>${displayModelName}</td>
      <td>${correctCount} (${percentCorrect}%)</td>
      <td>${partialCorrectCount} (${percentPartialCorrect}%)</td>
      <td>${difficultyCounts["Medium"]}</td>
      <td>${difficultyCounts["Hard"]}</td>
      <td>${difficultyCounts["Very Hard"]}</td>
      <td>${totalCount}</td>
      <td>${difficultyCounts["Unattempted"]}</td>
      <td>${categoryCounts.math}</td>
      <td>${categoryCounts.probability}</td>
      <td>${categoryCounts.geometry}</td>
      <td>${categoryCounts.logic_puzzle}</td>
      <td>${categoryCounts.image_only}</td>
      <td>${categoryCounts.text_only}</td>
      <td>${categoryCounts.mixed_input}</td>
      <td>${categoryCounts.language}</td>
      <td>${categoryCounts.abstract}</td>
    </tr>
  `;

  const detailRow = `
    <tr>
      <td colspan="18" style="padding: 0; border: none;">
        <div class="collapse" id="${collapseId}">
          <div class="p-3">
            <strong>Correct:</strong> ${correctList}<br>
            <strong>Partially Correct:</strong> ${partialList}
          </div>
        </div>
      </td>
    </tr>
  `;

  return summaryRow + detailRow;
}


async function displayResults() {
  const container = document.getElementById("resultsContainer");
  const totalByDifficulty = await getTotalPuzzlesPerDifficulty();

  // Parse category data
  const categoryMap = await new Promise((resolve, reject) => {
    Papa.parse("data/categories.csv", {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const map = {};
        results.data.forEach(row => map[row.id] = row);
        resolve(map);
      },
      error: err => reject(err)
    });
  });

  let statsArray = [];
  for (const model of models) {
    const stats = await getModelAccuracy(model, totalByDifficulty, categoryMap);
    statsArray.push(stats);
  }

  statsArray.sort((a, b) => {
    const accA = a.totalCount > 0 ? a.correctCount / a.totalCount : 0;
    const accB = b.totalCount > 0 ? b.correctCount / b.totalCount : 0;
    return accB - accA;
  });

  let html = `
    <div style="overflow-x:auto;">
      <table class="table table-striped table-sm">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Model</th>
            <th># Correct</th>
            <th># Partially Correct</th>
            <th>Medium</th>
            <th>Hard</th>
            <th>Very Hard</th>
            <th>Attempted</th>
            <th>Unattempted</th>
            <th>Math</th>
            <th>Prob</th>
            <th>Geo</th>
            <th>Logic</th>
            <th>Image</th>
            <th>Text</th>
            <th>Mixed</th>
            <th>Lang</th>
            <th>Abstract</th>
          </tr>
        </thead>
        <tbody>
  `;

  statsArray.forEach((stat, idx) => {
    html += createTableRow(idx + 1, stat);
  });

  html += `</tbody></table></div>`;
  container.innerHTML = html;
}

displayResults();
