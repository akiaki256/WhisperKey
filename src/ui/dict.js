// 音声辞書タブ
// 一つの項目(カード) = 変換後ひとつと、変換前いくつか(多対一)
// 入力欄から離れたとき・変換前を消したとき・項目を消したときに、辞書をまるごと保存する(すぐ効く)
// 画面の並びは読み込んだときだけ作り、保存のたびに作り直さない(入力中の空の欄が消えないように)

const dictList = document.getElementById("dict-list");

// アイコンだけのボタンを作る。glyph は Segoe Fluent Icons の文字
function iconButton(glyph, title) {
  const button = document.createElement("button");
  button.className = "icon-button";
  button.title = title;
  button.innerHTML = `<span class="icon">${glyph}</span>`;
  return button;
}

// 変換前の入力欄ひとつ(右に × ボタン)
function createBeforeRow(value) {
  const row = document.createElement("div");
  row.className = "dict-before-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "dict-before";
  input.value = value;
  input.placeholder = "話した言葉";

  const remove = iconButton("&#xE711;", "この変換前を消す");
  remove.classList.add("dict-remove-before");
  remove.addEventListener("click", () => {
    const card = row.closest(".pair-card");
    row.remove();
    updateRemoveButtons(card);
    saveDict();
  });

  row.append(input, remove);
  return row;
}

// 変換前が一つしかないときは × を隠す(項目ごと消したいときは右端のごみ箱を使う)
function updateRemoveButtons(card) {
  const rows = card.querySelectorAll(".dict-before-row");
  rows.forEach((row) => {
    row.querySelector(".dict-remove-before").hidden = rows.length === 1;
  });
}

// 項目ひとつ分のカード。group は { after, befores: [...] }
function createDictCard(group) {
  const card = document.createElement("div");
  card.className = "card pair-card";

  // 左: 変換前
  const befores = document.createElement("div");
  befores.className = "pair-left";
  befores.innerHTML = `<div class="field-label">変換前</div><div class="dict-before-rows"></div>`;
  const rows = befores.querySelector(".dict-before-rows");
  for (const before of group.befores) {
    rows.append(createBeforeRow(before));
  }

  const addBefore = document.createElement("button");
  addBefore.className = "subtle";
  addBefore.innerHTML = `<span class="icon">&#xE710;</span> 変換前を追加`;
  addBefore.addEventListener("click", () => {
    const row = createBeforeRow("");
    rows.append(row);
    updateRemoveButtons(card);
    row.querySelector("input").focus();
  });
  befores.append(addBefore);

  // 真ん中: 矢印
  const arrow = document.createElement("span");
  arrow.className = "icon pair-arrow";
  arrow.innerHTML = "&#xE72A;";

  // 右: 変換後
  const after = document.createElement("div");
  after.className = "pair-right";
  after.innerHTML = `<div class="field-label">変換後</div>`;
  const afterInput = document.createElement("input");
  afterInput.type = "text";
  afterInput.className = "dict-after-input";
  afterInput.value = group.after;
  afterInput.placeholder = "入力する言葉(空欄可)";
  after.append(afterInput);

  // 右端: 項目ごと消す
  const remove = iconButton("&#xE74D;", "この項目を消す");
  remove.classList.add("pair-delete");
  remove.addEventListener("click", () => {
    card.remove();
    saveDict();
  });

  card.append(befores, arrow, after, remove);
  updateRemoveButtons(card);
  return card;
}

// 画面のカードから、保存する形を作る
function collectDictGroups() {
  return [...dictList.querySelectorAll(".pair-card")].map((card) => ({
    after: card.querySelector(".dict-after-input").value,
    befores: [...card.querySelectorAll(".dict-before")].map((input) => input.value),
  }));
}

async function saveDict() {
  const result = await window.pywebview.api.save_dict(collectDictGroups());
  showError(result.error);
}

// カードを少しのあいだ光らせて、見える位置まで動かす(どのカードのことか伝えるため)
function flashCard(card) {
  card.scrollIntoView({ block: "nearest" });
  card.classList.remove("flash");
  void card.offsetWidth;   // いったん描き直させて、続けて光らせても毎回アニメーションが始まるようにする
  card.classList.add("flash");
}

// 音声辞書タブのお知らせの帯(数秒で消える)
let dictNoticeTimer = null;
function showDictNotice(message) {
  const notice = document.getElementById("dict-notice");
  notice.textContent = message;
  notice.hidden = false;
  clearTimeout(dictNoticeTimer);
  dictNoticeTimer = setTimeout(() => { notice.hidden = true; }, 5000);
}

// 変換後が同じカードがほかにあれば、そちらに変換前を移して一枚にまとめる(多対一)
// 戻り値: まとめたら true
function mergeSameAfter(card) {
  const after = card.querySelector(".dict-after-input").value;
  const target = [...dictList.querySelectorAll(".pair-card")].find(
    (other) => other !== card && other.querySelector(".dict-after-input").value === after,
  );
  if (!target) return false;

  const existing = [...target.querySelectorAll(".dict-before")].map((input) => input.value);
  const rows = target.querySelector(".dict-before-rows");
  for (const input of card.querySelectorAll(".dict-before")) {
    if (input.value !== "" && !existing.includes(input.value)) {
      rows.append(createBeforeRow(input.value));
    }
  }
  card.remove();
  updateRemoveButtons(target);
  flashCard(target);
  showDictNotice(`「${after}」の項目にまとめました`);
  return true;
}

// 入力履歴で選んだ言葉を、変換前に入れた新しいカードにする(history.js から呼ばれる)
// すでにどこかの変換前にあれば、新しく作らずにそのカードを見せる
function addDictFromHistory(text) {
  showTab("dict");
  const existing = [...dictList.querySelectorAll(".dict-before")].find((input) => input.value === text);
  if (existing) {
    const card = existing.closest(".pair-card");
    flashCard(card);
    existing.focus();
    showDictNotice(`「${text}」はすでに登録されています`);
    return;
  }

  const card = createDictCard({ after: "", befores: [text] });
  dictList.prepend(card);
  flashCard(card);
  card.querySelector(".dict-after-input").focus();   // あとは正しい言葉を打つだけ
}

// どの入力欄でも、離れたとき(change)に保存する
// 変換後を変えたときは、同じ変換後のカードがあればまとめてから保存する
dictList.addEventListener("change", (e) => {
  if (!e.target.matches("input")) return;
  if (e.target.matches(".dict-after-input")) {
    mergeSameAfter(e.target.closest(".pair-card"));
  }
  saveDict();
});

// 新しい項目は一番上に足す(追加してすぐ打ち込めるように)
document.getElementById("btn-add-dict").addEventListener("click", () => {
  const card = createDictCard({ after: "", befores: [""] });
  dictList.prepend(card);
  card.querySelector(".dict-before").focus();
});

async function loadDict() {
  const groups = await window.pywebview.api.get_dict();
  dictList.innerHTML = "";
  for (const group of groups) {
    dictList.append(createDictCard(group));
  }
}

window.addEventListener("pywebviewready", loadDict);
