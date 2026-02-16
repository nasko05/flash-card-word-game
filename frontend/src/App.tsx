import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import {
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  signIn,
  signOut,
  signUp
} from "aws-amplify/auth";
import { amplifyConfigured } from "./awsConfig";
import "./App.css";

type FlashCard = {
  id: string;
  spanish: string;
  bulgarian: string;
};

type StudyMode = "es_to_bg" | "bg_to_es";

type BulkUploadError = {
  row: number;
  message: string;
};

type BulkUploadResponse = {
  savedCount: number;
  rejectedCount: number;
  errors?: BulkUploadError[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";

function questionLabel(mode: StudyMode) {
  return mode === "es_to_bg" ? "Spanish" : "Bulgarian";
}

function answerLabel(mode: StudyMode) {
  return mode === "es_to_bg" ? "Bulgarian" : "Spanish";
}

function questionValue(card: FlashCard, mode: StudyMode) {
  return mode === "es_to_bg" ? card.spanish : card.bulgarian;
}

function answerValue(card: FlashCard, mode: StudyMode) {
  return mode === "es_to_bg" ? card.bulgarian : card.spanish;
}

function toErrorMessage(error: unknown) {
  if (error instanceof Error) {
    if (error.message.includes("Failed to fetch")) {
      return `${error.message} Check API URL/CORS and regenerate frontend env with scripts/generate-frontend-env.sh.`;
    }
    return error.message;
  }

  return "Something went wrong.";
}

function normalizeHeader(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "");
}

function toCellString(value: unknown) {
  return String(value ?? "").trim();
}

async function parseBulkXlsxFile(file: File) {
  const XLSX = await import("xlsx");
  const fileBytes = await file.arrayBuffer();
  const workbook = XLSX.read(fileBytes, { type: "array" });

  if (!workbook.SheetNames.length) {
    throw new Error("The XLSX file has no sheets.");
  }

  const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json<unknown[]>(firstSheet, {
    header: 1,
    raw: false,
    blankrows: false
  });

  if (rows.length < 2) {
    throw new Error("The XLSX file must contain a header row and at least one data row.");
  }

  const headerRow = Array.isArray(rows[0]) ? rows[0] : [];
  const normalizedHeaders = headerRow.map(normalizeHeader);

  const spanishColumnIndex = normalizedHeaders.findIndex(
    (columnName) => columnName === "spanish" || columnName === "espanol" || columnName === "español"
  );
  const bulgarianColumnIndex = normalizedHeaders.findIndex(
    (columnName) =>
      columnName === "bulgarian" ||
      columnName === "bulgariantranslation" ||
      columnName === "translationbg"
  );

  if (spanishColumnIndex === -1 || bulgarianColumnIndex === -1) {
    throw new Error("Header row must contain 'spanish' and 'bulgarian' columns.");
  }

  const items = rows
    .slice(1)
    .flatMap((rawRow) => {
      if (!Array.isArray(rawRow)) {
        return [];
      }

      const spanish = toCellString(rawRow[spanishColumnIndex]);
      const bulgarian = toCellString(rawRow[bulgarianColumnIndex]);

      if (!spanish && !bulgarian) {
        return [];
      }

      return [{ spanish, bulgarian }];
    });

  if (!items.length) {
    throw new Error("No non-empty data rows were found in the XLSX file.");
  }

  return items;
}

async function apiRequest(path: string, init: RequestInit = {}) {
  const session = await fetchAuthSession();
  const bearerToken =
    session.tokens?.idToken?.toString() || session.tokens?.accessToken?.toString() || "";

  if (!bearerToken) {
    throw new Error("Missing Cognito token. Please log in again.");
  }

  const requestUrl = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(requestUrl, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${bearerToken}`,
        ...(init.headers || {})
      }
    });
  } catch (_error) {
    throw new Error(`Failed to fetch ${requestUrl}`);
  }

  const rawBody = await response.text();
  let body: any = null;

  if (rawBody) {
    try {
      body = JSON.parse(rawBody);
    } catch {
      body = { message: rawBody };
    }
  }

  if (!response.ok) {
    throw new Error(body?.message || `Request failed with status ${response.status}.`);
  }

  return body;
}

function App() {
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmationCode, setConfirmationCode] = useState("");
  const [pendingConfirmationEmail, setPendingConfirmationEmail] = useState("");

  const [spanishWord, setSpanishWord] = useState("");
  const [bulgarianWord, setBulgarianWord] = useState("");
  const [wordBusy, setWordBusy] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkFileName, setBulkFileName] = useState("");

  const [cards, setCards] = useState<FlashCard[]>([]);
  const [revealedCards, setRevealedCards] = useState<Record<string, boolean>>({});
  const [drawBusy, setDrawBusy] = useState(false);
  const [studyMode, setStudyMode] = useState<StudyMode>("es_to_bg");

  const [gameCards, setGameCards] = useState<FlashCard[]>([]);
  const [gameIndex, setGameIndex] = useState(0);
  const [gameFlipped, setGameFlipped] = useState(false);
  const [gameBusy, setGameBusy] = useState(false);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const hasConfig = amplifyConfigured && Boolean(API_BASE_URL);
  const activeGameCard = gameCards[gameIndex] || null;

  useEffect(() => {
    let isMounted = true;

    async function checkSession() {
      try {
        await getCurrentUser();
        if (isMounted) {
          setIsAuthenticated(true);
        }
      } catch (_error) {
        if (isMounted) {
          setIsAuthenticated(false);
        }
      } finally {
        if (isMounted) {
          setIsBootstrapping(false);
        }
      }
    }

    if (!hasConfig) {
      setIsBootstrapping(false);
      return () => {
        isMounted = false;
      };
    }

    checkSession();

    return () => {
      isMounted = false;
    };
  }, [hasConfig]);

  function resetMessages() {
    setErrorMessage(null);
    setInfoMessage(null);
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();
    setAuthBusy(true);

    try {
      const loginEmail = email.trim();
      const result = await signIn({ username: loginEmail, password });

      if (!result.isSignedIn) {
        throw new Error(`Unexpected sign-in step: ${result.nextStep.signInStep}`);
      }

      setIsAuthenticated(true);
      setInfoMessage("Logged in successfully.");
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();
    setAuthBusy(true);

    try {
      const registerEmail = email.trim();
      const result = await signUp({
        username: registerEmail,
        password,
        options: {
          userAttributes: {
            email: registerEmail
          }
        }
      });

      if (result.nextStep.signUpStep === "CONFIRM_SIGN_UP") {
        setPendingConfirmationEmail(registerEmail);
        setInfoMessage("Registration successful. Check your email for the confirmation code.");
      } else {
        setPendingConfirmationEmail("");
        setInfoMessage("Registration successful. You can now log in.");
        setAuthMode("login");
      }
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleConfirmRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();
    setAuthBusy(true);

    try {
      if (!pendingConfirmationEmail) {
        throw new Error("No pending registration found. Register first.");
      }

      await confirmSignUp({
        username: pendingConfirmationEmail,
        confirmationCode: confirmationCode.trim()
      });

      setInfoMessage("Email confirmed. Log in with your new account.");
      setConfirmationCode("");
      setAuthMode("login");
      setPendingConfirmationEmail("");
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleSignOut() {
    resetMessages();

    try {
      await signOut();
      setIsAuthenticated(false);
      setCards([]);
      setRevealedCards({});
      setGameCards([]);
      setGameIndex(0);
      setGameFlipped(false);
      setInfoMessage("Logged out.");
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    }
  }

  async function handleWordUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();
    setWordBusy(true);

    try {
      const spanish = spanishWord.trim();
      const bulgarian = bulgarianWord.trim();

      if (!spanish || !bulgarian) {
        throw new Error("Please fill in both fields.");
      }

      await apiRequest("/words", {
        method: "POST",
        body: JSON.stringify({ spanish, bulgarian })
      });

      setSpanishWord("");
      setBulgarianWord("");
      setInfoMessage(`Saved word: ${spanish}`);
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setWordBusy(false);
    }
  }

  async function handleBulkFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    resetMessages();
    setBulkBusy(true);
    setBulkFileName(file.name);

    try {
      const items = await parseBulkXlsxFile(file);
      const response = (await apiRequest("/words/bulk", {
        method: "POST",
        body: JSON.stringify({ items })
      })) as BulkUploadResponse;

      const savedCount = response.savedCount || 0;
      const rejectedCount = response.rejectedCount || 0;
      const firstError = response.errors?.[0];

      if (rejectedCount > 0) {
        setInfoMessage(
          `Bulk upload complete. Saved ${savedCount}, rejected ${rejectedCount}. ${firstError ? `First issue (row ${firstError.row}): ${firstError.message}` : ""}`
        );
      } else {
        setInfoMessage(`Bulk upload complete. Saved ${savedCount} words.`);
      }
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setBulkBusy(false);
      setBulkFileName("");
      event.target.value = "";
    }
  }

  async function handleDownloadTemplate() {
    const XLSX = await import("xlsx");
    const workbook = XLSX.utils.book_new();
    const worksheet = XLSX.utils.aoa_to_sheet([
      ["spanish", "bulgarian"],
      ["aprender", "уча"],
      ["hablar", "говоря"],
      ["comer", "ям"]
    ]);

    XLSX.utils.book_append_sheet(workbook, worksheet, "words");
    XLSX.writeFile(workbook, "spanish-bulgarian-template.xlsx");
  }

  async function handleDrawCards() {
    resetMessages();
    setDrawBusy(true);

    try {
      const result = await apiRequest("/words/random?limit=50");
      const fetchedCards = (result?.items || []) as FlashCard[];

      setCards(fetchedCards);
      setRevealedCards({});
      setInfoMessage(
        fetchedCards.length
          ? `Loaded ${fetchedCards.length} flash cards.`
          : "No words available yet. Upload some first."
      );
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setDrawBusy(false);
    }
  }

  async function handleStartMiniGame() {
    resetMessages();
    setGameBusy(true);

    try {
      const result = await apiRequest("/words/random?limit=20");
      const fetchedCards = (result?.items || []) as FlashCard[];

      if (!fetchedCards.length) {
        setGameCards([]);
        setInfoMessage("No words available yet. Upload some first.");
        return;
      }

      setGameCards(fetchedCards);
      setGameIndex(0);
      setGameFlipped(false);
      setInfoMessage(`Mini-game ready with ${fetchedCards.length} cards.`);
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setGameBusy(false);
    }
  }

  function handleFlipGameCard() {
    if (!activeGameCard) {
      return;
    }

    setGameFlipped((current) => !current);
  }

  function handleNextGameCard() {
    if (!activeGameCard) {
      return;
    }

    if (gameIndex >= gameCards.length - 1) {
      const reviewedCount = gameCards.length;
      setGameCards([]);
      setGameIndex(0);
      setGameFlipped(false);
      setInfoMessage(`Mini-game complete. Reviewed ${reviewedCount} words.`);
      return;
    }

    setGameIndex((current) => current + 1);
    setGameFlipped(false);
  }

  function toggleCard(cardId: string) {
    setRevealedCards((current) => ({
      ...current,
      [cardId]: !current[cardId]
    }));
  }

  if (!hasConfig) {
    return (
      <main className="app-shell">
        <section className="panel">
          <h1>Missing frontend configuration</h1>
          <p>
            Populate <code>.env.local</code> with Cognito + API values. Start with
            <code>frontend/.env.example</code>.
          </p>
        </section>
      </main>
    );
  }

  if (isBootstrapping) {
    return (
      <main className="app-shell">
        <section className="panel">
          <h1>Checking session</h1>
          <p>Please wait...</p>
        </section>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="app-shell">
        <section className="panel auth-panel">
          <h1>Spanish Study App</h1>
          <p className="panel-subtitle">Sign in or register with Cognito to manage your flash cards.</p>

          <div className="tab-row">
            <button
              type="button"
              className={authMode === "login" ? "tab active" : "tab"}
              onClick={() => setAuthMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              className={authMode === "register" ? "tab active" : "tab"}
              onClick={() => setAuthMode("register")}
            >
              Register
            </button>
          </div>

          <form onSubmit={authMode === "login" ? handleLogin : handleRegister} className="form-stack">
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={authMode === "login" ? "current-password" : "new-password"}
                minLength={8}
                required
              />
            </label>

            <button type="submit" disabled={authBusy}>
              {authBusy ? "Please wait..." : authMode === "login" ? "Login" : "Create account"}
            </button>
          </form>

          {pendingConfirmationEmail ? (
            <form onSubmit={handleConfirmRegistration} className="form-stack confirm-form">
              <label>
                Confirmation code
                <input
                  type="text"
                  value={confirmationCode}
                  onChange={(event) => setConfirmationCode(event.target.value)}
                  placeholder="Enter email code"
                  required
                />
              </label>
              <button type="submit" disabled={authBusy}>
                Confirm registration
              </button>
            </form>
          ) : null}

          {errorMessage ? <p className="message error">{errorMessage}</p> : null}
          {infoMessage ? <p className="message info">{infoMessage}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className="panel dashboard-panel">
        <header className="dashboard-header">
          <div>
            <h1>Spanish → Bulgarian Flash Cards</h1>
            <p className="panel-subtitle">
              Add vocabulary and draw up to 50 random cards for revision.
            </p>
          </div>
          <button type="button" onClick={handleSignOut} className="secondary">
            Logout
          </button>
        </header>

        <section className="mode-switch-panel">
          <p className="mode-switch-title">Study direction</p>
          <div className="mode-switch-buttons">
            <button
              type="button"
              className={studyMode === "es_to_bg" ? "tab active" : "tab"}
              onClick={() => setStudyMode("es_to_bg")}
            >
              Spanish → Bulgarian
            </button>
            <button
              type="button"
              className={studyMode === "bg_to_es" ? "tab active" : "tab"}
              onClick={() => setStudyMode("bg_to_es")}
            >
              Bulgarian → Spanish
            </button>
          </div>
        </section>

        <form onSubmit={handleWordUpload} className="word-form">
          <label>
            Spanish word
            <input
              type="text"
              value={spanishWord}
              onChange={(event) => setSpanishWord(event.target.value)}
              placeholder="e.g. aprender"
              required
            />
          </label>

          <label>
            Bulgarian translation
            <input
              type="text"
              value={bulgarianWord}
              onChange={(event) => setBulgarianWord(event.target.value)}
              placeholder="e.g. уча"
              required
            />
          </label>

          <button type="submit" disabled={wordBusy}>
            {wordBusy ? "Saving..." : "Upload word"}
          </button>
        </form>

        <section className="bulk-upload-panel">
          <div className="bulk-upload-header">
            <h2>Bulk upload (XLSX)</h2>
            <button type="button" className="secondary" onClick={handleDownloadTemplate}>
              Download template
            </button>
          </div>
          <p className="bulk-upload-hint">
            Use an XLSX file with headers <code>spanish</code> and <code>bulgarian</code> in row 1.
          </p>
          <label>
            Upload XLSX file
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={handleBulkFileChange}
              disabled={bulkBusy}
            />
          </label>
          {bulkBusy ? <p className="bulk-upload-status">Processing {bulkFileName}...</p> : null}
        </section>

        <div className="cards-toolbar">
          <h2>Flash cards</h2>
          <button type="button" onClick={handleDrawCards} disabled={drawBusy}>
            {drawBusy ? "Drawing..." : "Draw random 50"}
          </button>
        </div>

        <div className="cards-grid">
          {cards.map((card, index) => {
            const isRevealed = revealedCards[card.id];

            return (
              <button
                type="button"
                key={`${card.id}-${index}`}
                className={isRevealed ? "card revealed" : "card"}
                onClick={() => toggleCard(card.id)}
                style={{ animationDelay: `${(index % 10) * 40}ms` }}
              >
                <span className="card-label">
                  {isRevealed ? answerLabel(studyMode) : questionLabel(studyMode)}
                </span>
                <span className="card-value">
                  {isRevealed ? answerValue(card, studyMode) : questionValue(card, studyMode)}
                </span>
                <span className="card-hint">Tap to flip</span>
              </button>
            );
          })}
        </div>

        <section className="mini-game-panel">
          <div className="cards-toolbar mini-game-toolbar">
            <h2>Mini-game (20 cards)</h2>
            <button type="button" onClick={handleStartMiniGame} disabled={gameBusy}>
              {gameBusy ? "Preparing..." : "Start mini-game"}
            </button>
          </div>

          {activeGameCard ? (
            <div className="mini-game-content">
              <p className="mini-game-progress">
                Card {gameIndex + 1} of {gameCards.length}
              </p>

              <button
                type="button"
                className={gameFlipped ? "card revealed mini-game-card" : "card mini-game-card"}
                onClick={handleFlipGameCard}
              >
                <span className="card-label">
                  {gameFlipped ? answerLabel(studyMode) : questionLabel(studyMode)}
                </span>
                <span className="card-value">
                  {gameFlipped
                    ? answerValue(activeGameCard, studyMode)
                    : questionValue(activeGameCard, studyMode)}
                </span>
                <span className="card-hint">Tap card to flip</span>
              </button>

              <div className="mini-game-actions">
                <button type="button" onClick={handleNextGameCard}>
                  {gameIndex >= gameCards.length - 1 ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          ) : (
            <p className="mini-game-empty">
              Start the mini-game to draw 20 random words, flip each card, and move to the next one.
            </p>
          )}
        </section>

        {errorMessage ? <p className="message error">{errorMessage}</p> : null}
        {infoMessage ? <p className="message info">{infoMessage}</p> : null}
      </section>
    </main>
  );
}

export default App;
