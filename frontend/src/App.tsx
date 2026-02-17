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
type PracticeMode = "flashcards" | "quiz_bg_to_es" | "quiz_es_to_bg" | "sentence_bg_to_es";
type QuizResult = {
  status: "exact" | "warning" | "wrong";
  expected: string;
};

type SentenceResult = {
  status: "exact" | "warning" | "wrong";
  canonicalAnswer: string;
};

type SentenceExercise = {
  id: string;
  promptBulgarian: string;
  personKey?: string;
  domain?: string;
  difficulty?: number;
  tense?: string;
};

type BulkUploadError = {
  row: number;
  message: string;
};

type BulkUploadResponse = {
  savedCount: number;
  rejectedCount: number;
  errors?: BulkUploadError[];
};

type ExportWordsResponse = {
  count: number;
  items: FlashCard[];
};

type SentenceNextResponse = {
  item?: SentenceExercise;
  message?: string;
};

type SentenceCheckResponse = {
  status: "exact" | "warning" | "wrong";
  isCorrect: boolean;
  message: string;
  canonicalAnswer: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";
const FLASHCARD_MODE: StudyMode = "es_to_bg";
const COMBINING_MARK_REGEX = /[\u0300-\u036f]/;
const SPANISH_VOWELS = new Set(["a", "e", "i", "o", "u"]);

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

function quizPromptLabel(mode: PracticeMode) {
  return mode === "quiz_bg_to_es" ? "Bulgarian word" : "Spanish word";
}

function quizExpectedLabel(mode: PracticeMode) {
  return mode === "quiz_bg_to_es" ? "Spanish answer" : "Bulgarian answer";
}

function quizPromptValue(card: FlashCard, mode: PracticeMode) {
  return mode === "quiz_bg_to_es" ? card.bulgarian : card.spanish;
}

function quizExpectedValue(card: FlashCard, mode: PracticeMode) {
  return mode === "quiz_bg_to_es" ? card.spanish : card.bulgarian;
}

function normalizeWhitespaceKeepingCase(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function normalizeWhitespace(value: string) {
  return normalizeWhitespaceKeepingCase(value).toLowerCase();
}

function normalizeSpanishQuizAnswer(value: string) {
  const normalized = normalizeWhitespace(value).normalize("NFD");
  let rebuilt = "";
  let previousBaseChar = "";

  for (const char of normalized) {
    if (COMBINING_MARK_REGEX.test(char)) {
      if (SPANISH_VOWELS.has(previousBaseChar)) {
        continue;
      }

      rebuilt += char;
      continue;
    }

    rebuilt += char;
    previousBaseChar = char;
  }

  return rebuilt.normalize("NFC");
}

function evaluateQuizAnswer(mode: PracticeMode, provided: string, expected: string) {
  if (mode === "quiz_bg_to_es") {
    const providedComparable = normalizeSpanishQuizAnswer(provided);
    const expectedComparable = normalizeSpanishQuizAnswer(expected);

    if (providedComparable !== expectedComparable) {
      return { isCorrect: false, warning: false };
    }

    const providedStrict = normalizeWhitespaceKeepingCase(provided).normalize("NFC");
    const expectedStrict = normalizeWhitespaceKeepingCase(expected).normalize("NFC");

    return {
      isCorrect: true,
      warning: providedStrict !== expectedStrict
    };
  }

  const providedComparable = normalizeWhitespace(provided);
  const expectedComparable = normalizeWhitespace(expected);

  if (providedComparable !== expectedComparable) {
    return { isCorrect: false, warning: false };
  }

  return {
    isCorrect: true,
    warning: normalizeWhitespaceKeepingCase(provided) !== normalizeWhitespaceKeepingCase(expected)
  };
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
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);

  const [cards, setCards] = useState<FlashCard[]>([]);
  const [revealedCards, setRevealedCards] = useState<Record<string, boolean>>({});
  const [drawBusy, setDrawBusy] = useState(false);
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("flashcards");

  const [gameCards, setGameCards] = useState<FlashCard[]>([]);
  const [gameIndex, setGameIndex] = useState(0);
  const [gameFlipped, setGameFlipped] = useState(false);
  const [gameBusy, setGameBusy] = useState(false);

  const [quizCards, setQuizCards] = useState<FlashCard[]>([]);
  const [quizIndex, setQuizIndex] = useState(0);
  const [quizInput, setQuizInput] = useState("");
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [quizCorrectCount, setQuizCorrectCount] = useState(0);
  const [quizAnsweredCount, setQuizAnsweredCount] = useState(0);
  const [quizBusy, setQuizBusy] = useState(false);

  const [sentenceExercise, setSentenceExercise] = useState<SentenceExercise | null>(null);
  const [sentenceInput, setSentenceInput] = useState("");
  const [sentenceResult, setSentenceResult] = useState<SentenceResult | null>(null);
  const [sentenceAnsweredCount, setSentenceAnsweredCount] = useState(0);
  const [sentenceCorrectCount, setSentenceCorrectCount] = useState(0);
  const [sentenceBusy, setSentenceBusy] = useState(false);
  const [sentenceCheckBusy, setSentenceCheckBusy] = useState(false);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const hasConfig = amplifyConfigured && Boolean(API_BASE_URL);
  const activeGameCard = gameCards[gameIndex] || null;
  const activeQuizCard = quizCards[quizIndex] || null;

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

  useEffect(() => {
    if (!isUploadDialogOpen) {
      return undefined;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsUploadDialogOpen(false);
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isUploadDialogOpen]);

  function resetMessages() {
    setErrorMessage(null);
    setInfoMessage(null);
  }

  function openUploadDialog() {
    setIsUploadDialogOpen(true);
  }

  function closeUploadDialog() {
    setIsUploadDialogOpen(false);
  }

  function resetQuizState() {
    setQuizCards([]);
    setQuizIndex(0);
    setQuizInput("");
    setQuizResult(null);
    setQuizCorrectCount(0);
    setQuizAnsweredCount(0);
  }

  function resetSentenceState() {
    setSentenceExercise(null);
    setSentenceInput("");
    setSentenceResult(null);
    setSentenceAnsweredCount(0);
    setSentenceCorrectCount(0);
  }

  function handlePracticeModeChange(mode: PracticeMode) {
    resetMessages();
    setPracticeMode(mode);
    resetQuizState();
    resetSentenceState();
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
      setIsUploadDialogOpen(false);
      setCards([]);
      setRevealedCards({});
      setGameCards([]);
      setGameIndex(0);
      setGameFlipped(false);
      setPracticeMode("flashcards");
      resetQuizState();
      resetSentenceState();
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

  async function handleDownloadWords() {
    resetMessages();
    setDownloadBusy(true);

    try {
      const result = (await apiRequest("/words/export")) as ExportWordsResponse;
      const items = result?.items || [];

      if (!items.length) {
        setInfoMessage("No words available yet for export.");
        return;
      }

      const XLSX = await import("xlsx");
      const workbook = XLSX.utils.book_new();
      const worksheet = XLSX.utils.aoa_to_sheet([
        ["spanish", "bulgarian"],
        ...items.map((item) => [item.spanish, item.bulgarian])
      ]);
      const dateStamp = new Date().toISOString().slice(0, 10);

      XLSX.utils.book_append_sheet(workbook, worksheet, "words");
      XLSX.writeFile(workbook, `spanish-bulgarian-export-${dateStamp}.xlsx`);
      setInfoMessage(`Downloaded ${items.length} words.`);
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setDownloadBusy(false);
    }
  }

  async function handleDrawCards() {
    resetMessages();
    setDrawBusy(true);

    try {
      const result = await apiRequest("/words/random?limit=20");
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

  async function handleStartQuiz() {
    if (practiceMode === "flashcards") {
      return;
    }

    resetMessages();
    setQuizBusy(true);

    try {
      const result = await apiRequest("/words/random?limit=20");
      const fetchedCards = (result?.items || []) as FlashCard[];

      if (!fetchedCards.length) {
        resetQuizState();
        setInfoMessage("No words available yet. Upload some first.");
        return;
      }

      setQuizCards(fetchedCards);
      setQuizIndex(0);
      setQuizInput("");
      setQuizResult(null);
      setQuizCorrectCount(0);
      setQuizAnsweredCount(0);
      setInfoMessage(`Quiz ready with ${fetchedCards.length} words.`);
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setQuizBusy(false);
    }
  }

  function handleSubmitQuizAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();

    if (!activeQuizCard || quizResult || practiceMode === "flashcards") {
      return;
    }

    const providedAnswer = quizInput.trim();
    if (!providedAnswer) {
      setErrorMessage("Enter an answer before checking.");
      return;
    }

    const expectedAnswer = quizExpectedValue(activeQuizCard, practiceMode);
    const evaluation = evaluateQuizAnswer(practiceMode, providedAnswer, expectedAnswer);
    setQuizAnsweredCount((current) => current + 1);

    if (evaluation.isCorrect) {
      setQuizCorrectCount((current) => current + 1);
      if (evaluation.warning) {
        setQuizResult({ status: "warning", expected: expectedAnswer });
        setInfoMessage("Correct, but be careful with accent or case.");
        return;
      }

      setQuizResult({ status: "exact", expected: expectedAnswer });
      setInfoMessage("Correct.");
      return;
    }

    setQuizResult({ status: "wrong", expected: expectedAnswer });
    setInfoMessage("Not quite. Review the expected answer and continue.");
  }

  function handleNextQuizWord() {
    if (!activeQuizCard || !quizResult) {
      return;
    }

    if (quizIndex >= quizCards.length - 1) {
      const totalAnswered = quizAnsweredCount;
      const totalCorrect = quizCorrectCount;
      resetQuizState();
      setInfoMessage(`Quiz complete. Score: ${totalCorrect}/${totalAnswered}.`);
      return;
    }

    setQuizIndex((current) => current + 1);
    setQuizInput("");
    setQuizResult(null);
    resetMessages();
  }

  async function fetchNextSentenceExercise() {
    const result = (await apiRequest("/sentences/next")) as SentenceNextResponse;
    const item = result?.item || null;

    if (!item) {
      setSentenceExercise(null);
      setInfoMessage(result?.message || "No sentence exercises are available yet.");
      return false;
    }

    setSentenceExercise(item);
    setSentenceInput("");
    setSentenceResult(null);
    return true;
  }

  async function handleStartSentenceExercise() {
    resetMessages();
    setSentenceBusy(true);

    try {
      setSentenceAnsweredCount(0);
      setSentenceCorrectCount(0);
      const loaded = await fetchNextSentenceExercise();
      if (loaded) {
        setInfoMessage("Sentence practice started.");
      }
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setSentenceBusy(false);
    }
  }

  async function handleCheckSentenceAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();

    if (!sentenceExercise || sentenceResult) {
      return;
    }

    const answer = sentenceInput.trim();
    if (!answer) {
      setErrorMessage("Enter a full Spanish sentence before checking.");
      return;
    }

    setSentenceCheckBusy(true);
    try {
      const result = (await apiRequest("/sentences/check", {
        method: "POST",
        body: JSON.stringify({
          sentenceId: sentenceExercise.id,
          answer
        })
      })) as SentenceCheckResponse;

      setSentenceResult({
        status: result.status,
        canonicalAnswer: result.canonicalAnswer
      });
      setSentenceAnsweredCount((current) => current + 1);
      if (result.isCorrect) {
        setSentenceCorrectCount((current) => current + 1);
      }
      setInfoMessage(result.message);
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setSentenceCheckBusy(false);
    }
  }

  async function handleNextSentenceExercise() {
    if (!sentenceExercise) {
      return;
    }

    resetMessages();
    setSentenceBusy(true);
    try {
      await fetchNextSentenceExercise();
    } catch (error) {
      setErrorMessage(toErrorMessage(error));
    } finally {
      setSentenceBusy(false);
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
            <h1>Spanish Practice</h1>
            <p className="panel-subtitle">
              Add vocabulary and practice with flash cards, word quizzes, and sentence translation.
            </p>
          </div>
          <button type="button" onClick={handleSignOut} className="secondary">
            Logout
          </button>
        </header>

        <section className="mode-switch-panel">
          <p className="mode-switch-title">Practice mode</p>
          <div className="mode-switch-buttons">
            <button
              type="button"
              className={practiceMode === "flashcards" ? "tab active" : "tab"}
              onClick={() => handlePracticeModeChange("flashcards")}
            >
              Flash cards
            </button>
            <button
              type="button"
              className={practiceMode === "quiz_bg_to_es" ? "tab active" : "tab"}
              onClick={() => handlePracticeModeChange("quiz_bg_to_es")}
            >
              Quiz: BG → ES
            </button>
            <button
              type="button"
              className={practiceMode === "quiz_es_to_bg" ? "tab active" : "tab"}
              onClick={() => handlePracticeModeChange("quiz_es_to_bg")}
            >
              Quiz: ES → BG
            </button>
            <button
              type="button"
              className={practiceMode === "sentence_bg_to_es" ? "tab active" : "tab"}
              onClick={() => handlePracticeModeChange("sentence_bg_to_es")}
            >
              Sentences: BG → ES
            </button>
          </div>
        </section>

        <div className="upload-dialog-trigger">
          <button type="button" onClick={openUploadDialog}>
            Upload words
          </button>
          <button type="button" className="secondary" onClick={handleDownloadWords} disabled={downloadBusy}>
            {downloadBusy ? "Preparing..." : "Download words"}
          </button>
        </div>

        {practiceMode === "flashcards" ? (
          <>
            <div className="cards-toolbar">
              <h2>Flash cards</h2>
              <button type="button" onClick={handleDrawCards} disabled={drawBusy}>
                {drawBusy ? "Drawing..." : "Draw random 20"}
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
                      {isRevealed ? answerLabel(FLASHCARD_MODE) : questionLabel(FLASHCARD_MODE)}
                    </span>
                    <span className="card-value">
                      {isRevealed
                        ? answerValue(card, FLASHCARD_MODE)
                        : questionValue(card, FLASHCARD_MODE)}
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
                      {gameFlipped ? answerLabel(FLASHCARD_MODE) : questionLabel(FLASHCARD_MODE)}
                    </span>
                    <span className="card-value">
                      {gameFlipped
                        ? answerValue(activeGameCard, FLASHCARD_MODE)
                        : questionValue(activeGameCard, FLASHCARD_MODE)}
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
          </>
        ) : practiceMode === "sentence_bg_to_es" ? (
          <section className="quiz-panel">
            <div className="cards-toolbar quiz-toolbar">
              <h2>Sentence practice: Bulgarian → Spanish</h2>
              <button type="button" onClick={handleStartSentenceExercise} disabled={sentenceBusy}>
                {sentenceBusy ? "Preparing..." : "Start sentence practice"}
              </button>
            </div>

            {sentenceExercise ? (
              <div className="quiz-content">
                <p className="mini-game-progress">Translate this sentence into Spanish</p>
                <p className="quiz-prompt-label">BULGARIAN SENTENCE</p>
                <p className="quiz-prompt-value">{sentenceExercise.promptBulgarian}</p>

                <form onSubmit={handleCheckSentenceAnswer} className="quiz-form">
                  <label>
                    Spanish translation
                    <input
                      type="text"
                      value={sentenceInput}
                      onChange={(event) => setSentenceInput(event.target.value)}
                      placeholder="Type the full sentence in Spanish"
                      disabled={Boolean(sentenceResult) || sentenceCheckBusy}
                      required
                    />
                  </label>

                  <div className="quiz-actions">
                    <button
                      type="submit"
                      disabled={
                        sentenceBusy ||
                        sentenceCheckBusy ||
                        Boolean(sentenceResult) ||
                        !sentenceInput.trim()
                      }
                    >
                      {sentenceCheckBusy ? "Checking..." : "Check sentence"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={handleNextSentenceExercise}
                      disabled={sentenceBusy || !sentenceResult}
                    >
                      Next sentence
                    </button>
                  </div>
                </form>

                {sentenceResult ? (
                  <p
                    className={
                      sentenceResult.status === "exact"
                        ? "quiz-result correct"
                        : sentenceResult.status === "warning"
                          ? "quiz-result warning"
                          : "quiz-result wrong"
                    }
                  >
                    {sentenceResult.status === "exact"
                      ? "Correct."
                      : sentenceResult.status === "warning"
                        ? `Correct, but be careful with accent or case. Canonical: ${sentenceResult.canonicalAnswer}`
                        : `Incorrect. Canonical: ${sentenceResult.canonicalAnswer}`}
                  </p>
                ) : null}

                <p className="quiz-score">
                  Score: {sentenceCorrectCount}/{sentenceAnsweredCount}
                </p>
              </div>
            ) : (
              <p className="quiz-empty">
                Start sentence practice to get natural day-to-day Bulgarian prompts.
              </p>
            )}
          </section>
        ) : (
          <section className="quiz-panel">
            <div className="cards-toolbar quiz-toolbar">
              <h2>
                {practiceMode === "quiz_bg_to_es"
                  ? "Word quiz: Bulgarian → Spanish"
                  : "Word quiz: Spanish → Bulgarian"}
              </h2>
              <button type="button" onClick={handleStartQuiz} disabled={quizBusy}>
                {quizBusy ? "Preparing..." : "Start quiz (20 words)"}
              </button>
            </div>

            {activeQuizCard ? (
              <div className="quiz-content">
                <p className="mini-game-progress">
                  Word {quizIndex + 1} of {quizCards.length}
                </p>
                <p className="quiz-prompt-label">{quizPromptLabel(practiceMode)}</p>
                <p className="quiz-prompt-value">{quizPromptValue(activeQuizCard, practiceMode)}</p>

                <form onSubmit={handleSubmitQuizAnswer} className="quiz-form">
                  <label>
                    {quizExpectedLabel(practiceMode)}
                    <input
                      type="text"
                      value={quizInput}
                      onChange={(event) => setQuizInput(event.target.value)}
                      placeholder="Type your answer"
                      disabled={Boolean(quizResult)}
                      required
                    />
                  </label>

                  <div className="quiz-actions">
                    <button
                      type="submit"
                      disabled={quizBusy || Boolean(quizResult) || !quizInput.trim()}
                    >
                      Check answer
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={handleNextQuizWord}
                      disabled={!quizResult}
                    >
                      {quizIndex >= quizCards.length - 1 ? "Finish quiz" : "Next word"}
                    </button>
                  </div>
                </form>

                {quizResult ? (
                  <p
                    className={
                      quizResult.status === "exact"
                        ? "quiz-result correct"
                        : quizResult.status === "warning"
                          ? "quiz-result warning"
                          : "quiz-result wrong"
                    }
                  >
                    {quizResult.status === "exact"
                      ? "Correct."
                      : quizResult.status === "warning"
                        ? `Correct, but be careful with accent or case. Correct word: ${quizResult.expected}`
                        : `Incorrect. Expected: ${quizResult.expected}`}
                  </p>
                ) : null}

                <p className="quiz-score">
                  Score: {quizCorrectCount}/{quizAnsweredCount}
                </p>
              </div>
            ) : (
              <p className="quiz-empty">
                Start the quiz to draw 20 random words and answer them one by one.
              </p>
            )}
          </section>
        )}

        {isUploadDialogOpen ? (
          <div className="upload-dialog-backdrop" onClick={closeUploadDialog}>
            <section
              className="upload-dialog"
              role="dialog"
              aria-modal="true"
              aria-label="Upload words"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="upload-dialog-header">
                <button type="button" className="secondary upload-dialog-close" onClick={closeUploadDialog}>
                  Close
                </button>
              </div>

              <h2>Upload words</h2>

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

              {errorMessage ? <p className="message error">{errorMessage}</p> : null}
              {infoMessage ? <p className="message info">{infoMessage}</p> : null}
            </section>
          </div>
        ) : null}

        {!isUploadDialogOpen && errorMessage ? <p className="message error">{errorMessage}</p> : null}
        {!isUploadDialogOpen && infoMessage ? <p className="message info">{infoMessage}</p> : null}
      </section>
    </main>
  );
}

export default App;
