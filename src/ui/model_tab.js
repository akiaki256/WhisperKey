// モデルタブのモデルの一覧(ラジオボタンのカード)
//
// カードの右側に、そのモデルが手元にあるかを出す
// - 手元にある:     「ダウンロード済み」
// - 手元に無い:     「ダウンロード(約 1.5 GB)」ボタン。押すと Python が別のスレッドで取りに行く
// - ダウンロード中: くるくる回る矢印と「ダウンロード中 42%」
// 手元に無いモデルは、ダウンロードが終わるまで選べない(ラジオボタンを押せなくする)
// 進み具合と終わったことは、Python から onModelProgress / onModelDownloaded で届く

const modelList = document.getElementById("model-list");

function modelCard(name) {
  return modelList.querySelector(`.radio-card[data-model="${name}"]`);
}

function showModelError(message) {
  const errorEl = document.getElementById("model-error");
  errorEl.textContent = message ?? "";
  errorEl.hidden = !message;
}

// カードの右側を、状態に合わせて作り直す
// state: "downloaded" / "missing" / "downloading"
function showModelState(card, state, progress = 0) {
  const status = card.querySelector(".model-status");
  const radio = card.querySelector("input");
  radio.disabled = state !== "downloaded";
  card.classList.toggle("unavailable", state !== "downloaded");

  if (state === "downloaded") {
    status.innerHTML = `<span class="model-ready"><span class="icon">&#xE73E;</span> ダウンロード済み</span>`;
  } else if (state === "downloading") {
    status.innerHTML = `<span class="model-downloading"><span class="icon spinning">&#xE72C;</span> <span class="model-percent"></span></span>`;
    status.querySelector(".model-percent").textContent = `ダウンロード中 ${Math.floor(progress * 100)}%`;
  } else {
    status.innerHTML = `<button class="model-download"><span class="icon">&#xE896;</span> <span class="model-size"></span></button>`;
    status.querySelector(".model-size").textContent = `ダウンロード(${card.dataset.size})`;
    status.querySelector("button").addEventListener("click", async (e) => {
      e.preventDefault();   // カード(label)を押したことにして、ラジオボタンが動かないように
      showModelError(null);
      const result = await window.pywebview.api.download_model(card.dataset.model);
      if (result.error) {
        showModelError(result.error);
      } else {
        showModelState(card, "downloading", 0);
      }
    });
  }
}

// モデルの一覧を、ラジオボタンのカードで作る。models は [{value, name, desc, size, downloaded, downloading}, ...]
function buildModelList(container, models, current) {
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
    card.querySelector(".card-title").textContent = model.name;
    card.querySelector(".card-desc").textContent = model.desc;
    radio.addEventListener("change", () => saveSetting("model_size", model.value));

    container.append(card);
    showModelState(card, model.downloading ? "downloading" : model.downloaded ? "downloaded" : "missing");
  }
}

// ---- Python から届く知らせ(main_window.py の _download_in_background) ----

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
  if (!ok) showModelError(error);
}
