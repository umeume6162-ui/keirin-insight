"use strict";

const storageKey = "horse-insight.research-sheet";
const sheetOrigin = "https://docs.google.com";
const allowedId = /^[A-Za-z0-9_-]{20,128}$/;
const links = document.getElementById("research-links");
const settings = document.getElementById("settings");
const form = document.getElementById("sheet-form");
const input = document.getElementById("sheet-link");
const remove = document.getElementById("remove-sheet");
const status = document.getElementById("connection-status");

function idFromUrl(value) {
  try {
    const url = new URL(value.trim());
    if (url.origin !== sheetOrigin || url.username || url.password) return "";
    return url.pathname.match(/^\/spreadsheets\/d\/([A-Za-z0-9_-]{20,128})(?:\/edit)?\/?$/)?.[1] ?? "";
  } catch {
    return "";
  }
}

function sheetUrl(id) {
  return `${sheetOrigin}/spreadsheets/d/${id}/edit`;
}

function savedId() {
  try {
    const id = localStorage.getItem(storageKey) ?? "";
    return allowedId.test(id) ? id : "";
  } catch {
    return "";
  }
}

function save(id) {
  try {
    if (id) localStorage.setItem(storageKey, id);
    else localStorage.removeItem(storageKey);
    return true;
  } catch {
    return false;
  }
}

function displaySheet(id, message) {
  links.hidden = !id;
  remove.hidden = !id;
  settings.open = !id;
  input.value = id ? sheetUrl(id) : "";
  for (const link of links.querySelectorAll("a[data-tab]")) {
    if (id) link.href = `${sheetUrl(id)}#gid=${link.dataset.tab}`;
    else link.removeAttribute("href");
  }
  status.textContent = message;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const id = idFromUrl(input.value);
  if (!id) {
    status.textContent = "Google スプレッドシートの編集画面のURLを入力してください。";
    input.focus();
    return;
  }
  const persisted = save(id);
  displaySheet(id, persisted ? "研究台帳のリンクを保存しました。" : "この画面でリンクを開けます。ブラウザへの保存はできませんでした。");
  links.querySelector("a")?.focus();
});

remove.addEventListener("click", () => {
  const removed = save("");
  displaySheet("", removed ? "保存したリンクを解除しました。" : "この画面のリンクを解除しました。ブラウザの保存内容は確認できませんでした。");
  input.focus();
});

const launch = new URLSearchParams(location.hash.slice(1)).get("sheet") ?? "";
if (allowedId.test(launch)) {
  const persisted = save(launch);
  history.replaceState(history.state, "", `${location.pathname}${location.search}`);
  displaySheet(launch, persisted ? "研究台帳のリンクを保存しました。" : "この画面でリンクを開けます。ブラウザへの保存はできませんでした。");
} else {
  displaySheet(savedId(), "");
}
