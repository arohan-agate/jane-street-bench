async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status}`);
  }
  return await res.json();
}

async function getLastPuzzleOutputs() {
  const container = document.getElementById("lastPuzzleContainer");
  if (!container) return;

  const css = `
    #lastPuzzleContainer {
      padding: 0.5rem;
    }

    #lastPuzzleContainer table {
      table-layout: fixed;
      width: 100%;
      border-collapse: collapse;
      margin-top: 2rem;
    }

    #lastPuzzleContainer td pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font-family: inherit;
      background: transparent;
    }

    /* Tighter cell padding */
    #lastPuzzleContainer td,
    #lastPuzzleContainer th {
      padding: 0.5rem;
      vertical-align: top;
    }

    /* Optional: header background */
    #lastPuzzleContainer th {
      background: #f8f9fa;
    }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  try {
    const results = await fetchJSON("results/last_month_solutions.json");
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
        Error loading last-month solutions.
      </div>
    `;
  }
}

async function showOfficialSolution() {
  const container = document.getElementById("officialSolutionContainer");
  if (!container) return;

  // ── STEP: overwrite the “last month's puzzle” link using puzzleLink from CSV ──
  Papa.parse("data/puzzles.csv", {
    download: true,
    header: true,
    skipEmptyLines: true,
    complete: (results) => {
      const data = results.data;
      if (data.length < 2) {
        // no action if there is no "last" row
      } else {
        const row = data[1];
        const link = row.puzzleLink || "#";
        const aTag = document.getElementById("puzzleLink");
        if (aTag) {
          aTag.href = link;
          aTag.innerText = "last month's puzzle";
        }
      }
    },
    error: (err) => {
      console.error("Error parsing CSV for puzzleLink:", err);
    }
  });
  // ─────────────────────────────────────────────────────────────────────────

  const css = `
    #officialSolutionContainer {
      padding: 0.5rem 1rem;
    }
    #officialSolutionContainer img {
      max-width: 600px;
      width: 100%;
      height: auto;
      display: block;
      margin-top: 1rem;
    }
    #officialSolutionContainer pre {
      background: #f8f9fa;
      padding: 0.75rem;
      white-space: pre-wrap;
      word-break: break-word;
    }
    #officialSolutionContainer .section-heading {
      margin-top: 0.5rem;
      margin-bottom: 0.5rem;
    }
  `;
  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  try {
    Papa.parse("data/puzzles.csv", {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const data = results.data;
        if (data.length < 2) {
          container.innerHTML = "<div class='alert alert-warning'>No last-month puzzle found.</div>";
          return;
        }
        const row = data[1];

        // Only show the OFFICIAL SOLUTION details (no puzzle statement).
        const solText = row.solutionText || "(no solution text)";
        const finalAnswer = row.answer || "(no final answer)";
        const numSolvers = row.numSolvers || "N/A";
        const puzzleName = row.name || "";
        const solHasImage = row.solutionHasImages === "TRUE" || row.solutionHasImages === true;
        console.log(solHasImage);

        let solImgHtml = "";
        let foundImage = false;

        if (solHasImage) {
        const exts = ["png","jpg","jpeg"];
        const safeName = encodeURIComponent(puzzleName);

        for (const ext of exts) {
            const solImgPath = `data/solution_images/${safeName}/0_0.${ext}`;
            console.log("→ trying solution image at:", solImgPath);

            const imgTester = new Image();
            imgTester.onload = () => {

            solImgHtml = `<img src="${solImgPath}" alt="Solution Image">`;
            console.log("→ loaded solution image:", solImgPath);
            foundImage = true;

            document.getElementById("officialSolutionContainer").insertAdjacentHTML("beforeend", solImgHtml);
            };
            imgTester.onerror = () => {
            console.log(`→ no image at ${solImgPath}, trying next extension…`);
            };
            imgTester.src = solImgPath;

            if (foundImage) break;
        }
        }


        container.innerHTML = `
          <h2 class="section-heading">Last Month's Official Solution</h2>
          <p><strong>Final Answer:</strong> ${finalAnswer}</p>
          <p><strong>Number of Solvers:</strong> ${numSolvers}</p>
          <h5>Solution:</h5>
          <pre>${solText}</pre>
          ${solImgHtml}
        `;
      },
      error: (err) => {
        console.error(err);
        container.innerHTML = `<div class="alert alert-danger">Error loading puzzle CSV.</div>`;
      }
    });
  } catch (e) {
    console.error(e);
    container.innerHTML = `<div class="alert alert-danger">Error loading official solution.</div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  showOfficialSolution();
  getLastPuzzleOutputs();
});
