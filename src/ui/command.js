// 音声実行タブ
// 一つのカード = キーワード → 種類(URL / ファイル)と開くもの
// 入力欄から離れたとき・種類を変えたとき・消したときに、一覧をまるごと保存する(すぐ効く)
// キーワードか開くものが空のカードは、入力の途中とみなして Python 側で保存しない

const commandList = document.getElementById("command-list");
let commandTypes = [];   // [[保存値, 表示ラベル], ...](Python の config_store.COMMAND_TYPES)

const PATH_PLACEHOLDERS = {
  url: "https://...",
  file: "開くファイルの場所",
};

// 種類に合わせて、開くものの案内と「参照」ボタンを切り替える
function updatePathField(card) {
  const tag = card.querySelector(".command-type").value;
  card.querySelector(".command-path").placeholder = PATH_PLACEHOLDERS[tag] ?? "";
  card.querySelector(".command-browse").hidden = tag !== "file";
}

// コマンドひとつ分のカード。row は { keyword, tag, path }
function createCommandCard(row) {
  const card = document.createElement("div");
  card.className = "card pair-card";

  // 左: キーワード
  const left = document.createElement("div");
  left.className = "pair-left";
  left.innerHTML = `<div class="field-label">キーワード</div>`;
  const keyword = document.createElement("input");
  keyword.type = "text";
  keyword.className = "command-keyword";
  keyword.value = row.keyword;
  keyword.placeholder = "話す言葉";
  left.append(keyword);

  // 真ん中: 矢印
  const arrow = document.createElement("span");
  arrow.className = "icon pair-arrow";
  arrow.innerHTML = "&#xE72A;";

  // 右: 種類と開くもの
  const right = document.createElement("div");
  right.className = "pair-right";
  right.innerHTML = `<div class="field-label">開くもの</div>`;

  const type = document.createElement("select");
  type.className = "command-type";
  for (const [value, label] of commandTypes) {
    type.add(new Option(label, value, false, value === row.tag));
  }

  const pathRow = document.createElement("div");
  pathRow.className = "field-row";
  const path = document.createElement("input");
  path.type = "text";
  path.className = "command-path";
  path.value = row.path;

  const browse = document.createElement("button");
  browse.className = "command-browse";
  browse.textContent = "参照";
  browse.addEventListener("click", async () => {
    const chosen = await window.pywebview.api.choose_file();
    if (chosen) {
      path.value = chosen;
      saveCommands();
    }
  });
  pathRow.append(path, browse);
  right.append(type, pathRow);

  // 右端: 消す
  const remove = iconButton("&#xE74D;", "このコマンドを消す");
  remove.classList.add("pair-delete");
  remove.addEventListener("click", () => {
    card.remove();
    saveCommands();
  });

  card.append(left, arrow, right, remove);
  updatePathField(card);
  return card;
}

// 画面のカードから、保存する形を作る
function collectCommands() {
  return [...commandList.querySelectorAll(".pair-card")].map((card) => ({
    keyword: card.querySelector(".command-keyword").value,
    tag: card.querySelector(".command-type").value,
    path: card.querySelector(".command-path").value,
  }));
}

async function saveCommands() {
  const result = await window.pywebview.api.save_commands(collectCommands());
  showError(result.error);
}

// 入力欄から離れたとき・種類を選んだとき(どちらも change)に保存する
commandList.addEventListener("change", (e) => {
  if (e.target.matches(".command-type")) {
    updatePathField(e.target.closest(".pair-card"));
  }
  saveCommands();
});

// 新しいコマンドは一番上に足す
document.getElementById("btn-add-command").addEventListener("click", () => {
  const card = createCommandCard({ keyword: "", tag: commandTypes[0][0], path: "" });
  commandList.prepend(card);
  card.querySelector(".command-keyword").focus();
});

async function loadCommands() {
  const data = await window.pywebview.api.get_commands();
  commandTypes = data.types;
  commandList.innerHTML = "";
  for (const row of data.rows) {
    commandList.append(createCommandCard(row));
  }
}

window.addEventListener("pywebviewready", loadCommands);
