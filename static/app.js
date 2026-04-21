const DEFAULT_API = "http://127.0.0.1:8001";
const TOKEN_KEY = "wm.jwt";
const API_KEY = "wm.api";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  apiBase: localStorage.getItem(API_KEY) || DEFAULT_API,
  categories: [],
};

const authPanel = document.getElementById("auth-panel");
const dashboardPanel = document.getElementById("dashboard-panel");
const authMsg = document.getElementById("auth-msg");
const expenseMsg = document.getElementById("expense-msg");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const expenseForm = document.getElementById("expense-form");
const logoutBtn = document.getElementById("logout-btn");
const apiInput = document.getElementById("api-base-input");
const saveApiBtn = document.getElementById("save-api-btn");
const categorySelect = document.getElementById("category-select");
const expensesTbody = document.getElementById("expenses-tbody");
const totalMonth = document.getElementById("total-month");
const categoryBars = document.getElementById("category-bars");

apiInput.value = state.apiBase;
expenseForm.elements.date.valueAsDate = new Date();

function setToken(token) {
  state.token = token || "";
  if (state.token) localStorage.setItem(TOKEN_KEY, state.token);
  else localStorage.removeItem(TOKEN_KEY);
}

function setApi(base) {
  state.apiBase = String(base || DEFAULT_API).replace(/\/+$/, "");
  localStorage.setItem(API_KEY, state.apiBase);
  apiInput.value = state.apiBase;
}

function showAuth(message, isError = false) {
  authMsg.textContent = message;
  authMsg.className = isError ? "full-row" : "full-row muted";
  if (isError) authMsg.style.color = "#ff6b81";
  else authMsg.style.color = "";
}

function showExpenseMessage(message, isError = false) {
  expenseMsg.textContent = message;
  expenseMsg.style.color = isError ? "#ff6b81" : "#8ea0cb";
}

function fmtMoney(v) {
  return Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);

  let response;
  try {
    response = await fetch(`${state.apiBase}${path}`, { ...options, headers });
  } catch (_e) {
    throw new Error(`Cannot reach API at ${state.apiBase}`);
  }

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && state.token) {
      setToken("");
      renderAuth();
      throw new Error("Session expired. Please sign in again.");
    }
    const detail = payload?.detail || payload;
    if (Array.isArray(detail)) {
      throw new Error(detail.map((x) => `${(x.loc || []).join(".")}: ${x.msg}`).join("; "));
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return payload;
}

function renderAuth() {
  authPanel.classList.remove("hidden");
  dashboardPanel.classList.add("hidden");
  logoutBtn.classList.add("hidden");
}

function renderDashboard() {
  authPanel.classList.add("hidden");
  dashboardPanel.classList.remove("hidden");
  logoutBtn.classList.remove("hidden");
}

async function loadCategories() {
  state.categories = await api("/categories");
  categorySelect.innerHTML = state.categories.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
}

async function loadExpenses() {
  const expenses = await api("/expenses");
  expensesTbody.innerHTML = expenses.length
    ? expenses
        .map(
          (e) => `
      <tr>
        <td>${e.date}</td>
        <td>${e.category_name}</td>
        <td>${e.description}</td>
        <td>$${fmtMoney(e.amount)}</td>
        <td><button class="btn btn-danger" data-expense-id="${e.id}">Delete</button></td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="5" class="muted">No expenses logged yet.</td></tr>`;

  document.querySelectorAll("[data-expense-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const expenseId = btn.getAttribute("data-expense-id");
      try {
        await api(`/expenses/${expenseId}`, { method: "DELETE" });
        await Promise.all([loadExpenses(), loadSummary()]);
      } catch (e) {
        showExpenseMessage(e.message, true);
      }
    });
  });
}

async function loadSummary() {
  const summary = await api("/expenses/summary");
  totalMonth.textContent = `$${fmtMoney(summary.total_spent_this_month)}`;

  const max = Math.max(...summary.by_category.map((x) => x.total), 1);
  categoryBars.innerHTML = summary.by_category.length
    ? summary.by_category
        .map((row) => {
          const pct = Math.max(5, Math.round((row.total / max) * 100));
          return `
          <div class="bar-row">
            <span>${row.category}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span>$${fmtMoney(row.total)}</span>
          </div>
        `;
        })
        .join("")
    : `<p class="muted">No spending this month.</p>`;
}

async function loadDashboardData() {
  await Promise.all([loadCategories(), loadExpenses(), loadSummary()]);
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(loginForm);
  const body = new URLSearchParams();
  body.set("username", String(form.get("username")));
  body.set("password", String(form.get("password")));

  try {
    const tokenData = await api("/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    setToken(tokenData.access_token);
    showAuth("Login successful.");
    renderDashboard();
    await loadDashboardData();
  } catch (err) {
    showAuth(err.message, true);
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(registerForm);
  const payload = {
    email: String(form.get("email") || "").trim(),
    username: String(form.get("username") || "").trim(),
    password: String(form.get("password") || ""),
  };
  if (!payload.email.includes("@")) return showAuth("Use a valid email.", true);
  if (payload.username.length < 3) return showAuth("Username must be at least 3 characters.", true);
  if (payload.password.length < 8) return showAuth("Password must be at least 8 characters.", true);

  try {
    await api("/register", { method: "POST", body: JSON.stringify(payload) });
    showAuth("Registration complete. You can sign in now.");
    registerForm.reset();
  } catch (err) {
    showAuth(err.message, true);
  }
});

expenseForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(expenseForm);
  const payload = {
    amount: Number(form.get("amount")),
    category_id: Number(form.get("category_id")),
    description: String(form.get("description") || "").trim(),
    date: String(form.get("date")),
  };
  if (!payload.description) return showExpenseMessage("Description is required.", true);
  if (!payload.date) return showExpenseMessage("Date is required.", true);

  try {
    await api("/expenses", { method: "POST", body: JSON.stringify(payload) });
    showExpenseMessage("Expense added.");
    expenseForm.reset();
    expenseForm.elements.date.valueAsDate = new Date();
    await Promise.all([loadExpenses(), loadSummary()]);
  } catch (err) {
    showExpenseMessage(err.message, true);
  }
});

logoutBtn.addEventListener("click", () => {
  setToken("");
  renderAuth();
});

saveApiBtn.addEventListener("click", () => {
  setApi(apiInput.value);
  showAuth(`API saved: ${state.apiBase}`);
});

(async () => {
  if (!state.token) return renderAuth();
  try {
    renderDashboard();
    await loadDashboardData();
  } catch (_e) {
    setToken("");
    renderAuth();
  }
})();
