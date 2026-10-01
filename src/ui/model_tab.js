// モデルタブのモデルの一覧(ラジオボタンのカード)
//
// カードの右側に、そのモデルが手元にあるかを出す
// - 手元にある:     「ダウンロード済み」とごみ箱ボタン。確認の帯を出してから消す
//                   選ばれているモデルのごみ箱は出さない(style.css)
// - 手元に無い:     「ダウンロード(約 1.5 GB)」ボタン。押すと Python が別のスレッドで取りに行く
// - ダウンロード中: くるくる回る矢印と「ダウンロード中 42%」
// 手元に無いモデルは、ダウンロードが終わるまで選べない(ラジオボタンを押せなくする)
// 進み具合と終わったことは、Python から onModelProgress / onModelDownloaded で届く
//
// 入力補正タブの LLM のカード(correction.js)も、この仕組みを使う。ラジオボタンは無く、エラーはそのタブの帯に出る

const modelList = document.getElementById("model-list");

function modelCard(name) {
  return document.querySelector(`.card[data-model="${name}"]`);
}

// エラーは、カードのあるタブの帯に出す(カードを渡さなければモデルタブ)
function showModelError(message, card = null) {
  const errorEl = card?.closest("section").querySelector(".infobar.error") ?? document.getElementById("model-error");
  errorEl.textContent = message ?? "";
  errorEl.hidden = !message;
  if (message) errorEl.scrollIntoView({ block: "nearest" });   // 一覧を下までスクロールしていても見えるように
}

// カードの右側を、状態に合わせて作り直す
// state: "downloaded" / "missing" / "downloading"
function showModelState(card, state, progress = 0) {
  const status = card.querySelector(".model-status");
  const radio = card.querySelector("input[type=radio]");
  if (radio) radio.disabled = state !== "downloaded";
  card.classList.toggle("unavailable", state !== "downloaded");

  if (state === "downloaded") {
    status.innerHTML = `<span class="model-ready"><span class="icon">&#xE73E;</span> ダウンロード済み</span>
      <button class="icon-button model-delete" title="このモデルを削除"><span class="icon">&#xE74D;</span></button>`;
    status.querySelector("button").addEventListener("click", async (e) => {
      e.preventDefault();   // カード(label)を押したことにして、ラジオボタンが動かないように
      showModelError(null, card);
      // 確認の帯は、押したカードのすぐ下に出す(一覧の下に置くと、モデルが多いときに画面の外になる)
      const bar = document.getElementById("model-delete-confirm");
      card.after(bar);
      const answer = askConfirm(bar,
        `${card.dataset.model}(${card.dataset.size})を削除しますか?使うときは、もう一度ダウンロードが必要です`);
      bar.scrollIntoView({ block: "nearest" });
      const ok = await answer;
      if (!ok) return;
      const result = await window.pywebview.api.delete_model(card.dataset.model);
      if (result.error) {
        showModelError(result.error, card);
      } else {
        showModelState(card, "missing");
      }
    });
  } else if (state === "downloading") {
    status.innerHTML = `<span class="model-downloading"><span class="icon spinning">&#xE72C;</span> <span class="model-percent"></span></span>`;
    status.querySelector(".model-percent").textContent = `ダウンロード中 ${Math.floor(progress * 100)}%`;
  } else {
    status.innerHTML = `<button class="model-download"><span class="icon">&#xE896;</span> <span class="model-size"></span></button>`;
    status.querySelector(".model-size").textContent = `ダウンロード(${card.dataset.size})`;
    status.querySelector("button").addEventListener("click", async (e) => {
      e.preventDefault();   // カード(label)を押したことにして、ラジオボタンが動かないように
      showModelError(null, card);
      const result = await window.pywebview.api.download_model(card.dataset.model);
      if (result.error) {
        showModelError(result.error, card);
      } else {
        showModelState(card, "downloading", 0);
      }
    });
  }
}

// モデルの一覧を、ラジオボタンのカードで作る。models は [{value, name, desc, size, downloaded, downloading}, ...]
function buildModelList(container, models, current) {
  // 確認の帯がカードのあいだに入っていたら、作り直しで一緒に消えないよう、元の場所に戻す
  const bar = document.getElementById("model-delete-confirm");
  bar.hidden = true;
  container.after(bar);
  container.innerHTML = "";
  for (const model of models) {
    const card = document.createElement("label");
    card.className = "card radio-card";
    card.dataset.model = model.value;
    card.dataset.size = model.size;
    card.innerHTML = `
      <input type="radio" name="model_size">
      <div class="card-text">
        <div class="card-title"></div>
        <div class="card-desc"></div>
      </div>
      <div class="card-control model-status"></div>`;

    // 文字は textContent で入れる(innerHTML に混ぜない)
    const radio = card.querySelector("input");
    radio.value = model.value;
    radio.checked = model.value === current;
    card.querySelector(".card-title").textContent = `${model.name}(${model.size})`;
    card.querySelector(".card-desc").textContent = model.desc;
    radio.addEventListener("change", () => saveSetting("model_size", model.value));

    container.append(card);
    showModelState(card, model.downloading ? "downloading" : model.downloaded ? "downloaded" : "missing");
  }
}

// ---- 選ばれているモデルが手元に無いとき・読み込み中・読み込めたとき ----

let modelNoticeTimer = null;

function setModelNotice(message, autoHide = false) {
  const notice = document.getElementById("model-notice");
  clearTimeout(modelNoticeTimer);
  notice.textContent = message ?? "";
  notice.hidden = !message;
  if (message && autoHide) {
    modelNoticeTimer = setTimeout(() => { notice.hidden = true; }, 6000);
  }
}

// 画面を開いたとき(settings.js の loadSettings から)。state は "ready" / "missing" / "loading"
function showModelNotice(state, name) {
  if (state === "ready") return;
  showTab("model");
  if (state === "loading") {
    setModelNotice("モデルを読み込んでいます…");
  } else {
    setModelNotice(`選ばれているモデル(${name})がまだありません。ダウンロードすると、音声入力が使えるようになります`);
  }
}

// ---- Python から届く知らせ(main_window.py の _download_in_background / _load_if_needed) ----

function onModelLoading(name) {
  setModelNotice(`モデル(${name})を読み込んでいます…`);
}

function onModelReady(name) {
  setModelNotice(`準備ができました。音声入力が使えます(${name})`, true);
}

function onModelLoadFailed({ error }) {
  setModelNotice(null);
  showModelError(error);
}


function onModelProgress({ name, progress }) {
  const card = modelCard(name);
  const percent = card?.querySelector(".model-percent");
  if (percent) {
    percent.textContent = `ダウンロード中 ${Math.floor(progress * 100)}%`;
  } else if (card) {
    showModelState(card, "downloading", progress);
  }
}

function onModelDownloaded({ name, ok, error }) {
  const card = modelCard(name);
  if (card) showModelState(card, ok ? "downloaded" : "missing");
  if (!ok) showModelError(error, card);
}
