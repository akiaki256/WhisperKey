// 入力履歴タブ
// - スイッチ: オンの間だけ新しい入力を残す。オフにしても、今ある履歴には触らない
// - 残す件数: 減らしてあふれる分があるときは、確認の帯を出してから消す
// - 消去: 確認の帯を出してから、全部消す
// - 一覧: 新しい入力が来たら Python から onHistoryChanged で知らせが届く

const historyList = document.getElementById("history-list");
const historyToggle = document.getElementById("history-enabled");
const historyLimitSelect = document.getElementById("history-limit");
const clearHistoryButton = document.getElementById("btn-clear-history");
let historyEntries = [];
let historyLimit = 10;   // 今保存されている件数(確認で「やめる」を押したら、ここに戻す)

// 確認の帯を出して、「消す」なら true、「やめる」なら false を返す
function askConfirm(bar, message) {
  bar.querySelector(".infobar-text").textContent = message;
  bar.hidden = false;
  return new Promise((resolve) => {
    const answer = (ok) => {
      bar.hidden = true;
      bar.querySelector(".confirm-ok").onclick = null;
      bar.querySelector(".confirm-cancel").onclick = null;
      resolve(ok);
    };
    bar.querySelector(".confirm-ok").onclick = () => answer(true);
    bar.querySelector(".confirm-cancel").onclick = () => answer(false);
  });
}

// "2026-09-27T21:30:05" → "9/27 21:30"
function formatHistoryTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function createHistoryCard(entry) {
  const card = document.createElement("div");
  card.className = "card history-item";
  card.innerHTML = `
    <div class="card-text">
      <div class="history-text"></div>
      <div class="history-time"></div>
    </div>`;
  card.querySelector(".history-text").textContent = entry.text;
  card.querySelector(".history-time").textContent = formatHistoryTime(entry.time);

  // コピーしたら、少しのあいだチェックの印にする
  const copy = iconButton("&#xE8C8;", "コピー");
  copy.addEventListener("click", async () => {
    await window.pywebview.api.copy_text(entry.text);
    copy.innerHTML = `<span class="icon">&#xE73E;</span>`;
    setTimeout(() => { copy.innerHTML = `<span class="icon">&#xE8C8;</span>`; }, 1500);
  });

  card.append(copy);
  return card;
}

function renderHistory(entries) {
  historyEntries = entries;
  historyList.innerHTML = "";
  if (entries.length === 0) {
    historyList.innerHTML = `<div class="card"><div class="card-text"><div class="card-desc">まだ入力履歴はありません</div></div></div>`;
  }
  for (const entry of entries) {
    historyList.append(createHistoryCard(entry));
  }
  clearHistoryButton.disabled = entries.length === 0;
}

// Python 側で履歴が変わったときに呼ばれる(main_window.py の _on_history_changed)
function onHistoryChanged(entries) {
  renderHistory(entries);
}

function showHistoryToggle(enabled) {
  historyToggle.checked = enabled;
  document.getElementById("history-enabled-label").textContent = enabled ? "オン" : "オフ";
}

historyToggle.addEventListener("change", async () => {
  const value = await saveSetting("history_enabled", historyToggle.checked);
  if (value !== null) showHistoryToggle(value);
});

historyLimitSelect.addEventListener("change", async () => {
  const newLimit = Number(historyLimitSelect.value);
  const overflow = historyEntries.length - newLimit;
  if (overflow > 0) {
    const ok = await askConfirm(
      document.getElementById("history-limit-confirm"),
      `古い履歴 ${overflow} 件が消えます`,
    );
    if (!ok) {
      historyLimitSelect.value = historyLimit;
      return;
    }
  }
  const value = await saveSetting("history_limit", newLimit);   // あふれた分は Python が消して、一覧も届く
  if (value !== null) historyLimit = value;
  historyLimitSelect.value = historyLimit;
});

clearHistoryButton.addEventListener("click", async () => {
  const ok = await askConfirm(
    document.getElementById("history-clear-confirm"),
    `入力履歴 ${historyEntries.length} 件をすべて消去します。元には戻せません`,
  );
  if (!ok) return;
  const result = await window.pywebview.api.clear_history();
  showError(result.error);
});

async function loadHistory() {
  const s = await window.pywebview.api.get_settings();
  showHistoryToggle(s.values.history_enabled);
  historyLimit = s.values.history_limit;
  fillSelect(historyLimitSelect, s.history_limits, historyLimit);
  renderHistory(await window.pywebview.api.get_history());
}

window.addEventListener("pywebviewready", loadHistory);
