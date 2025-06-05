async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status}`);
  }
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

    /* Tighter cell padding */
    #currentPuzzleContainer td,
    #currentPuzzleContainer th {
      padding: 0.5rem;
      vertical-align: top;
    }

    /* Optional: make the header stand out */
    #currentPuzzleContainer th {
      background: #f8f9fa;
    }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  try {
    const results = await fetchJSON("results/curr_month_solutions.json");
    let rowsHtml = "";

    for (const [model, rec] of Object.entries(results)) {
      const ansList = rec.answers || [];
      let firstAns  = "";
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
      <h2>Current Month Puzzle</h2>
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
