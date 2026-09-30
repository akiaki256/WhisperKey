// 入力補正タブ(GPU版だけ。CPU版ではタブごと隠す)
// - スイッチ: オンにできるのは、入力履歴がオンで、モデルがあるとき(だめなら Python がエラーを返す)
// - 句読点補正: 入力補正がオンのときだけ動く。次の入力から効く
// - 待つ時間の上限: 1〜20 秒(0.5 秒刻み)。過ぎたら補正せずに入力する。次の入力から効く
// - モデルのカード: ダウンロード・削除の動きはモデルタブと同じ(model_tab.js の showModelState)
// - 準備中・準備完了・失敗は、Python から onCorrectionStatus で届く
// - よく使う言葉: 一つのカード = 言葉とよみがな。入力欄から離れたとき・消したときに、まるごと保存する(すぐ効く)
//   よみがなが空の言葉は LLM に渡さないので、枠を赤くして知らせる

const correctionToggle = document.getElementById("llm-correction");
const vocabList = document.getElementById("vocab-list");

function showCorrectionToggle(enabled) {
  correctionToggle.checked = enabled;
  document.getElementById("llm-correction-label").textContent = enabled ? "オン" : "オフ";
}

correctionToggle.addEventListener("change", async () => {
  const value = await saveSetting("llm_correction", correctionToggle.checked);
  showCorrectionToggle(value ?? !correctionToggle.checked);   // だめだったら元に戻す
});

// ---- 準備中・準備完了・失敗の知らせ ----

let correctionNoticeTimer = null;

// status は { state: "off" / "starting" / "ready" / "error", message }
// fromEvent: 変わったときの知らせか(画面を開いたときに「準備完了」を出し直さないため)
function showCorrectionStatus({ state, message }, fromEvent = true) {
  const notice = document.getElementById("correction-notice");
  const errorEl = document.getElementById("correction-error");
  clearTimeout(correctionNoticeTimer);
  notice.hidden = true;
  if (state === "starting") {
    notice.textContent = "入力補正を準備しています…(準備ができるまでは、補正せずに入力します)";
    notice.hidden = false;
  } else if (state === "ready" && fromEvent) {
    notice.textContent = "準備ができました。入力補正が使えます";
    notice.hidden = false;
    correctionNoticeTimer = setTimeout(() => { notice.hidden = true; }, 6000);
  }
  if (state === "error") {
    errorEl.textContent = message;
    errorEl.hidden = false;
    if (fromEvent) showTab("correction");   // 気づけるように、タブを開いて知らせる
  } else if (fromEvent) {
    errorEl.hidden = true;   // オフにし直した・立ち上げ直したら、前の失敗の知らせは消す
  }
}

// Python から(main_window.py の _on_correction_status)
function onCorrectionStatus(status) {
  showCorrectionStatus(status);
}

// ---- よく使う言葉 ----

function markMissingReading(input) {
  input.classList.toggle("missing", input.value.trim() === "");
  input.title = input.classList.contains("missing") ? "よみがなが空のため、LLM には渡しません" : "";
}

// 言葉ひとつ分のカード。row は { word, reading }
function createVocabCard(row) {
  const card = document.createElement("div");
  card.className = "card pair-card";

  const left = document.createElement("div");
  left.className = "pair-left";
  left.innerHTML = `<div class="field-label">言葉</div>`;
  const word = document.createElement("input");
  word.type = "text";
  word.className = "vocab-word";
  word.value = row.word;
  word.placeholder = "入力したい表記(例: 球泉洞)";
  left.append(word);

  const right = document.createElement("div");
  right.className = "pair-right";
  right.innerHTML = `<div class="field-label">よみがな</div>`;
  const reading = document.createElement("input");
  reading.type = "text";
  reading.className = "vocab-reading";
  reading.value = row.reading;
  reading.placeholder = "話したときの読み(例: きゅうせんどう)";
  markMissingReading(reading);
  reading.addEventListener("input", () => markMissingReading(reading));
  right.append(reading);

  const remove = iconButton("&#xE74D;", "この言葉を消す");
  remove.classList.add("pair-delete");
  remove.addEventListener("click", () => {
    card.remove();
    saveVocab();
  });

  card.append(left, right, remove);
  return card;
}

function collectVocabRows() {
  return [...vocabList.querySelectorAll(".pair-card")].map((card) => ({
    word: card.querySelector(".vocab-word").value,
    reading: card.querySelector(".vocab-reading").value,
  }));
}

async function saveVocab() {
  const result = await window.pywebview.api.save_vocab(collectVocabRows());
  showError(result.error);
}

function renderVocab(rows) {
  vocabList.innerHTML = "";
  for (const row of rows) {
    vocabList.append(createVocabCard(row));
  }
}

let vocabNoticeTimer = null;
function showVocabNotice(message) {
  const notice = document.getElementById("vocab-notice");
  notice.textContent = message;
  notice.hidden = false;
  clearTimeout(vocabNoticeTimer);
  vocabNoticeTimer = setTimeout(() => { notice.hidden = true; }, 5000);
}

// どの入力欄でも、離れたとき(change)に保存する
vocabList.addEventListener("change", (e) => {
  if (e.target.matches("input")) saveVocab();
});

// 新しい言葉は一番上に足す(追加してすぐ打ち込めるように)
document.getElementById("btn-add-vocab").addEventListener("click", () => {
  const card = createVocabCard({ word: "", reading: "" });
  vocabList.prepend(card);
  card.querySelector(".vocab-word").focus();
});

// 音声辞書の変換後のうち、前回取り込んだあとに増えたものを、よみがな空で一番上に足す
document.getElementById("btn-import-vocab").addEventListener("click", async () => {
  await saveVocab();   // 打ちかけの内容を先に残す(取り込みは保存されている一覧に足すため)
  const result = await window.pywebview.api.import_vocab_from_dict();
  showError(result.error);
  if (result.error) return;
  renderVocab(result.rows);
  showVocabNotice(result.added > 0
    ? `${result.added} 件を登録しました。よみがなを入れると、補正に使われます`
    : "新しく登録できる言葉はありません(前回取り込んだあとに、音声辞書の変換後が増えていません)");
});

// ---- 読み込み ----

async function loadCorrection() {
  const s = await window.pywebview.api.get_settings();
  if (s.edition !== "gpu") {
    document.querySelectorAll(".gpu-only").forEach((el) => { el.style.display = "none"; });
    return;
  }
  showCorrectionToggle(s.values.llm_correction);
  bindToggle(document.getElementById("llm-punctuation"), document.getElementById("llm-punctuation-label"),
    "llm_punctuation", s.values.llm_punctuation);

  // 待つ時間の上限(スライダーと数字。保存のしくみは settings.js の bindSlider)
  const timeoutRange = document.getElementById("llm-timeout-range");
  timeoutRange.min = s.llm_timeout.min;
  timeoutRange.max = s.llm_timeout.max;
  timeoutRange.step = s.llm_timeout.step;
  const showTimeout = bindSlider(
    "llm_timeout", timeoutRange, document.getElementById("llm-timeout-number"),
    (v) => Number(v).toFixed(1),
  );
  showTimeout(s.values.llm_timeout);

  const card = document.getElementById("llm-model-card");
  card.dataset.model = s.llm_model.value;
  card.dataset.size = s.llm_model.size;
  card.querySelector(".card-title").textContent = `${s.llm_model.name}(${s.llm_model.size})`;
  showModelState(card, s.llm_model.downloading ? "downloading" : s.llm_model.downloaded ? "downloaded" : "missing");

  showCorrectionStatus(s.correction_status, false);
  renderVocab(await window.pywebview.api.get_vocab());
}

window.addEventListener("pywebviewready", loadCorrection);
