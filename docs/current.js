async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return await res.json();
}

async function getCurrentPuzzleOutputs() {
  const container = document.getElementById("currentPuzzleContainer");
  if (!container) return;

  const css = `
    #currentPuzzleContainer {
      padding: 0.5rem;
    }
    #currentPuzzleContainer table {
      table-layout: fixed;
      width: 100%;
      border-collapse: collapse;
    }
    #currentPuzzleContainer td pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font-family: inherit;
      background: transparent;
    }
    #currentPuzzleContainer td,
    #currentPuzzleContainer th {
      padding: 0.5rem;
      vertical-align: top;
    }
    #currentPuzzleContainer th {
      background: #f8f9fa;
    }
  `;
  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  try {
    const results = await fetchJSON("results/curr_month_solutions.json");
    const modelOrder = [
      "gpt-4o-mini",
      "gpt-4o-2024-08-06",
      "gpt-4.1-2025-04-14",
      "o3-2025-04-16",
      "o4-mini-2025-04-16",
      "gemini-1.5-pro",
      "gemini-2.0-flash-exp",
      "claude-3-haiku-20240307",
      "claude-3-opus-20240229"
    ];

    let rowsHtml = "";
    for (const model of modelOrder) {
      const rec = results[model];
      if (!rec) continue;

      const ansList = rec.answers || [];
      let firstAns = "";
      let secondAns = "";

      for (const a of ansList) {
        if (a.attempt === 1) firstAns = a.answer || "";
        if (a.attempt === 2) secondAns = a.answer || "";
      }
      if (!firstAns)  firstAns  = "<em>No answer</em>";
      if (!secondAns) secondAns = "<em>No answer</em>";

      rowsHtml += `
        <tr>
          <td>${model}</td>
          <td><pre>${firstAns}</pre></td>
          <td><pre>${secondAns}</pre></td>
        </tr>
      `;
    }

    container.innerHTML = `
      <h2>Model Results</h2>
      <table class="table table-striped">
        <thead>
          <tr>
            <th style="width: 20%;">Model</th>
            <th style="width: 40%;">First Attempt</th>
            <th style="width: 40%;">Second Attempt</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;
  } catch (e) {
    console.error(e);
    container.innerHTML = `
      <div class="alert alert-danger">
        Error loading current‐month solutions.
      </div>
    `;
  }
}

document.addEventListener("DOMContentLoaded", getCurrentPuzzleOutputs);
