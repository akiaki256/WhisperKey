// 設定タブとモデルタブ
// 値を変えた瞬間に Python へ送って保存する。Python が直した値が返ってくるので、それを表示し直す
// (範囲外の数字を打ち込んでも、端に寄せた値が表示される)

// 一つの項目を保存する。直したあとの値を返す(失敗したら null)
// 失敗したときは、今開いているタブのエラーの帯に出す
async function saveSetting(key, value) {
  const result = await window.pywebview.api.update_setting(key, value);
  const errorEl = document.querySelector("section.active .infobar.error");

  if (result.error) {
    errorEl.textContent = result.error;
    errorEl.hidden = false;
    return null;
  }
  errorEl.hidden = true;
  document.getElementById("restart-notice").hidden = !result.restart_needed;
  return result.value;
}

// テーマを画面に当てる。"system" のときは印を外して、Windows のモードに任せる(style.css)
function applyTheme(theme) {
  if (theme === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

// スライダーと数字の入力欄を組にする
// スライダーを動かしている間は数字だけ変え、離したとき(change)に保存する
function bindSlider(key, rangeEl, numberEl, format) {
  const show = (value) => {
    rangeEl.value = value;
    numberEl.value = format(value);
  };

  rangeEl.addEventListener("input", () => {
    numberEl.value = format(rangeEl.value);
  });

  const save = async (raw) => {
    const value = await saveSetting(key, Number(raw));
    if (value !== null) show(value);
  };
  rangeEl.addEventListener("change", () => save(rangeEl.value));
  numberEl.addEventListener("change", () => save(numberEl.value));

  return show;
}

// ドロップダウンを作る。choices は [[保存値, 表示ラベル], ...]
// onSaved は保存できたあとに呼ぶ(テーマの切り替えなど)
function bindSelect(selectEl, key, choices, current, onSaved) {
  selectEl.innerHTML = "";
  for (const [value, label] of choices) {
    selectEl.add(new Option(label, value, false, value === current));
  }
  selectEl.addEventListener("change", async () => {
    const value = await saveSetting(key, selectEl.value);
    if (value !== null) {
      selectEl.value = value;
      if (onSaved) onSaved(value);
    }
  });
}

// モデルの一覧を、ラジオボタンのカードで作る。models は [{value, name, desc}, ...]
function buildModelList(container, models, current) {
  container.innerHTML = "";
  for (const model of models) {
    const card = document.createElement("label");
    card.className = "card radio-card";
    card.innerHTML = `
      <input type="radio" name="model_size">
      <div class="card-text">
        <div class="card-title"></div>
        <div class="card-desc"></div>
      </div>`;

    // 文字は textContent で入れる(innerHTML に混ぜない)
    const radio = card.querySelector("input");
    radio.value = model.value;
    radio.checked = model.value === current;
    card.querySelector(".card-title").textContent = model.name;
    card.querySelector(".card-desc").textContent = model.desc;

    radio.addEventListener("change", () => saveSetting("model_size", model.value));
    container.append(card);
  }
}

async function loadSettings() {
  const s = await window.pywebview.api.get_settings();

  applyTheme(s.values.theme);

  // 音量しきい値
  const volumeRange = document.getElementById("volume-range");
  volumeRange.min = s.volume.min;
  volumeRange.max = s.volume.max;
  volumeRange.step = 1;
  const showVolume = bindSlider(
    "volume_threshold", volumeRange, document.getElementById("volume-number"),
    (v) => Math.round(v),
  );
  showVolume(s.values.volume_threshold);

  // 無音時間
  const silenceRange = document.getElementById("silence-range");
  silenceRange.min = s.silence.min;
  silenceRange.max = s.silence.max;
  silenceRange.step = s.silence.step;
  const showSilence = bindSlider(
    "silence_duration", silenceRange, document.getElementById("silence-number"),
    (v) => Number(v).toFixed(1),
  );
  showSilence(s.values.silence_duration);

  // 言語・モデル・テーマ
  bindSelect(document.getElementById("language-select"), "language", s.languages, s.values.language);
  buildModelList(document.getElementById("model-list"), s.models, s.values.model_size);
  bindSelect(document.getElementById("theme-select"), "theme", s.themes, s.values.theme, applyTheme);
  document.getElementById("restart-notice").hidden = !s.restart_needed;
}

document.getElementById("btn-restart").addEventListener("click", () => {
  window.pywebview.api.restart();
});

document.getElementById("btn-legacy-config").addEventListener("click", () => {
  window.pywebview.api.open_legacy_config();
});

// pywebview の準備ができてから Python を呼ぶ
window.addEventListener("pywebviewready", loadSettings);
