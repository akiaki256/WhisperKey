// 設定タブの音量しきい値(レベルメーター一体型)
//
// - バー: 今の音量。設定タブを開いているあいだだけ、50ms ごとに Python から取ってくる
// - つまみ: しきい値。バーがつまみを超えたら、バーの色が変わる(「今の声なら録音が始まる」)
// - 目盛りは対数。そのままの数字だと、雑音くらいの小さい音がバーの左端に張りついて見えないため
//   バーとつまみは同じ目盛りなので、見た目の位置がそのまま一致する
// - つまみを離したとき・数字を打ち込んだときに保存する(すぐ効く)

const volumeRange = document.getElementById("volume-range");   // 0〜1000(目盛りの位置)
const volumeNumber = document.getElementById("volume-number"); // しきい値そのもの
const levelFill = document.getElementById("level-fill");

let logMin = 2;   // log10(しきい値の最小)。setupLevelMeter で入れ直す
let logMax = 4;
let displayLevel = 0;      // バーに見せている音量(下がるときはゆっくり)
let levelRequest = false;  // Python に取りに行っている途中か(重ねて頼まないように)

// 音量 → 目盛りの位置(0〜1)
function levelToPosition(value) {
  const p = (Math.log10(Math.max(value, 1)) - logMin) / (logMax - logMin);
  return Math.min(Math.max(p, 0), 1);
}

// 目盛りの位置(0〜1) → 音量
function positionToLevel(p) {
  return Math.round(10 ** (logMin + p * (logMax - logMin)));
}

function showThreshold(value) {
  volumeNumber.value = value;
  volumeRange.value = levelToPosition(value) * 1000;
}

async function saveThreshold(value) {
  const saved = await saveSetting("volume_threshold", value);
  if (saved !== null) showThreshold(saved);
}

function setupLevelMeter(min, max, current) {
  logMin = Math.log10(min);
  logMax = Math.log10(max);
  showThreshold(current);
}

// つまみを動かしているあいだは数字だけ変え、離したときに保存する
volumeRange.addEventListener("input", () => {
  volumeNumber.value = positionToLevel(volumeRange.value / 1000);
});
volumeRange.addEventListener("change", () => saveThreshold(positionToLevel(volumeRange.value / 1000)));
volumeNumber.addEventListener("change", () => saveThreshold(Number(volumeNumber.value)));

async function updateLevel() {
  const visible = document.getElementById("tab-settings").classList.contains("active");
  if (!visible || levelRequest || !window.pywebview) return;

  levelRequest = true;
  try {
    const level = await window.pywebview.api.get_level();
    // 上がるときはすぐ、下がるときはゆっくり(ちらつかず、声の山が見やすいように)
    displayLevel = Math.max(level, displayLevel * 0.8);
    levelFill.style.setProperty("--p", levelToPosition(displayLevel));
    levelFill.classList.toggle("over", displayLevel > Number(volumeNumber.value));
  } finally {
    levelRequest = false;
  }
}

setInterval(updateLevel, 50);
