// 設定タブとモデルタブ
// 値を変えた瞬間に Python へ送って保存する。Python が直した値が返ってくるので、それを表示し直す
// (範囲外の数字を打ち込んでも、端に寄せた値が表示される)

// 今開いているタブのエラーの帯に message を出す。null なら帯を隠す
function showError(message) {
  const errorEl = document.querySelector("section.active .infobar.error");
  errorEl.textContent = message ?? "";
  errorEl.hidden = !message;
}

// 一つの項目を保存する。直したあとの値を返す(失敗したら null)
async function saveSetting(key, value) {
  const result = await window.pywebview.api.update_setting(key, value);
  showError(result.error);
  if (result.error) {
    return null;
  }
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
  fillSelect(selectEl, choices, current);
  selectEl.addEventListener("change", async () => {
    const value = await saveSetting(key, selectEl.value);
    if (value !== null) {
      selectEl.value = value;
      if (onSaved) onSaved(value);
    }
  });
}

// ドロップダウンの中身だけを入れ直す(マイクの一覧の更新でも使う)
function fillSelect(selectEl, choices, current) {
  selectEl.innerHTML = "";
  for (const [value, label] of choices) {
    selectEl.add(new Option(label, value, false, value === current));
  }
}

// オン/オフのスイッチを保存につなぐ。横に「オン」「オフ」の文字を出す
function bindToggle(toggle, label, key, current) {
  const show = (enabled) => {
    toggle.checked = enabled;
    label.textContent = enabled ? "オン" : "オフ";
  };
  show(current);
  toggle.addEventListener("change", async () => {
    const value = await saveSetting(key, toggle.checked);
    if (value !== null) show(value);
  });
}

// 効果音の選択肢。選んでいた wav が消えていたら「見つかりません」を付けて残す(勝手に変えない)
function soundChoices(names, current) {
  const choices = [["", "なし"], ...names.map((name) => [name, name.replace(/\.wav$/i, "")])];
  if (current && !names.includes(current)) {
    choices.push([current, `${current.replace(/\.wav$/i, "")}(見つかりません)`]);
  }
  return choices;
}

// 試し聞き(今ドロップダウンで選んでいる音を鳴らす)
document.querySelectorAll(".sound-preview").forEach((button) => {
  button.addEventListener("click", () => {
    window.pywebview.api.play_sound(document.getElementById(button.dataset.for).value);
  });
});

// マイクの名前の一覧を、ドロップダウンの選択肢にする
// 今選んでいるマイクが外されていたら、「見つかりません」を付けて残す(勝手に別のマイクに変えない)
function micChoices(names, current) {
  const choices = names.map((name) => [name, name]);
  if (!names.includes(current)) {
    choices.push([current, `${current}(見つかりません)`]);
  }
  return choices;
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

  // 音量しきい値(レベルメーターと一体。しくみは level_meter.js)
  setupLevelMeter(s.volume.min, s.volume.max, s.values.volume_threshold);

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

  // ショートカットキー(変えるしくみは settings_shortcut.js)
  for (const [action, keyStr] of Object.entries(s.shortcuts)) {
    showShortcut(action, keyStr);
  }
  const failed = Object.entries(s.shortcut_errors);
  if (failed.length > 0) {
    // 起動時に登録できなかった。ショートカットタブを開いて知らせる
    showTab("shortcuts");
    showError(failed.map(([action, kind]) =>
      startupShortcutMessage(s.shortcut_labels[action], kind, s.shortcuts[action])).join("\n"));
  }

  // 入力モード
  showPushToTalk(s.values.push_to_talk);

  // マイク
  bindSelect(document.getElementById("mic-select"), "audio_device_name",
    micChoices(s.mics, s.values.audio_device_name), s.values.audio_device_name);

  // 言語・モデル・テーマ
  bindSelect(document.getElementById("language-select"), "language", s.languages, s.values.language);
  buildModelList(document.getElementById("model-list"), s.models, s.values.model_size);
  bindSelect(document.getElementById("theme-select"), "theme", s.themes, s.values.theme, applyTheme);
  bindSelect(document.getElementById("indicator-select"), "indicator_mode", s.indicator_modes, s.values.indicator_mode);

  // 効果音。選択肢は「なし」+ assets/sounds の wav(表示は .wav を外した名前)
  for (const select of document.querySelectorAll(".sound-select")) {
    const key = select.dataset.key;
    bindSelect(select, key, soundChoices(s.sounds, s.values[key]), s.values[key]);
  }
  bindToggle(document.getElementById("sound-padding"), document.getElementById("sound-padding-label"),
    "sound_padding", s.values.sound_padding);

  // 貼り付け
  bindToggle(document.getElementById("clipboard-private"), document.getElementById("clipboard-private-label"),
    "clipboard_private", s.values.clipboard_private);
  document.getElementById("restart-notice").hidden = !s.restart_needed;
}

// マイクの一覧を取り直して、current を選んだ状態にする
async function refreshMics(current) {
  const selectEl = document.getElementById("mic-select");
  const names = await window.pywebview.api.get_mics();
  fillSelect(selectEl, micChoices(names, current), current);
}

// マイクを差し直したとき用。今の選択はそのまま残す
document.getElementById("btn-refresh-mics").addEventListener("click", () => {
  refreshMics(document.getElementById("mic-select").value);
});

// Python 側で設定が変わったときに呼ばれる(main_window.py の _on_config_changed)
// 例: 選んでいたマイクが抜かれて、録音の係が「既定のデバイス」に書き換えたとき
// changed は変わった項目だけの { 項目名: 値 }
function onSettingsChanged(changed) {
  if ("audio_device_name" in changed) {
    refreshMics(changed.audio_device_name);
  }
  if ("push_to_talk" in changed) {
    showPushToTalk(changed.push_to_talk);
  }
}

// プッシュトゥトークのスイッチと、ショートカットタブの「入力モードの切り替え」の説明をそろえる
function showPushToTalk(enabled) {
  const toggle = document.getElementById("push-to-talk");
  toggle.checked = enabled;
  document.getElementById("push-to-talk-label").textContent = enabled ? "オン" : "オフ";
  document.getElementById("toggle-key-desc").textContent =
    enabled ? "押している間だけ録音します(プッシュトゥトーク)" : "録音のオン/オフを切り替えます";
}

document.getElementById("push-to-talk").addEventListener("change", async (e) => {
  const value = await saveSetting("push_to_talk", e.target.checked);
  if (value !== null) showPushToTalk(value);
});

document.getElementById("btn-restart").addEventListener("click", () => {
  window.pywebview.api.restart();
});

// pywebview の準備ができてから Python を呼ぶ
window.addEventListener("pywebviewready", loadSettings);
