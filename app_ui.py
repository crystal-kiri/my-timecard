"""Time card UI redesign.

This file is written so it can be imported in environments that do not have
Streamlit installed. When Streamlit is available, it runs the app. When it is
not available, the module still loads and exposes the pure utility functions,
and you can run the bundled tests with:

    python timecard_tool_redesign_streamlit.py --test

This keeps the business logic testable without changing the production app
behavior.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

try:
    import streamlit as st
    from streamlit_gsheets import GSheetsConnection
    from break_slider import break_slider
    STREAMLIT_AVAILABLE = True
except ModuleNotFoundError:
    st = None  # type: ignore[assignment]
    GSheetsConnection = None  # type: ignore[assignment]
    break_slider = None  # type: ignore[assignment]
    STREAMLIT_AVAILABLE = False


JST = timezone(timedelta(hours=+9), "JST")
URL = "https://docs.google.com/spreadsheets/d/1muQ7GR7RbVtOBYS3nV-xy7VCq66QqE04TqFxZo5ndtg/edit?gid=643044008#gid=643044008"
MAIN_GRAY = "#5F5871"


class MissingDependencyError(RuntimeError):
    """Raised when an optional runtime dependency is unavailable."""


def get_theme(now: Optional[datetime] = None) -> dict[str, str | bool]:
    """Return theme tokens based on JST time.

    Parameters
    ----------
    now:
        Optional datetime override for testing.
    """
    if now is None:
        now = datetime.now(JST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JST)

    is_night = now.hour >= 17 or now.hour < 8
    if is_night:
        return {
            "is_night": True,
            "bg_color": "#EDE6F5",
            "disp_text": "#6B6181",
            "box_bg": "rgba(255, 255, 255, 0.72)",
            "clock_col": "#8A7FB1",
        }
    return {
        "is_night": False,
        "bg_color": "#F8F0F6",
        "disp_text": "#6B6181",
        "box_bg": "rgba(255,255,255,0.86)",
        "clock_col": "#8A7FB1",
    }


def calc_work_duration(start_str: Any, end_str: Any, break_minutes: Any) -> Optional[str]:
    """Calculate HH:MM work duration.

    Returns None for missing or invalid times.
    Negative durations are clamped to 00:00 to preserve the original behavior.
    """
    if pd.isna(start_str) or pd.isna(end_str):
        return None

    try:
        start_dt = datetime.strptime(str(start_str), "%H:%M")
        end_dt = datetime.strptime(str(end_str), "%H:%M")
        break_val = int(break_minutes) if pd.notna(break_minutes) else 0

        total_minutes = int((end_dt - start_dt).total_seconds() // 60) - break_val
        if total_minutes < 0:
            total_minutes = 0

        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    except Exception:
        return None


def require_streamlit() -> None:
    """Fail with a clear message if Streamlit runtime dependencies are missing."""
    if not STREAMLIT_AVAILABLE:
        raise MissingDependencyError(
            "streamlit / streamlit_gsheets / break_slider が見つかりません。\n"
            "このファイルは Streamlit 実行環境で動かしてください。\n"
            "ローカルなら例: pip install streamlit streamlit-gsheets\n"
            "テストだけ行う場合は: python <this_file> --test"
        )


def read_member_names(conn: Any) -> list[str]:
    """Read member names from Google Sheets."""
    df_members = conn.read(spreadsheet=URL, worksheet="スタッフ名簿", ttl=60)

    if df_members is None or df_members.empty or "名前" not in df_members.columns:
        raise ValueError("スタッフ名簿が空か、名前列がありません")

    names = (
        df_members["名前"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    if not names:
        raise ValueError("スタッフ名簿に名前がありません")
    return names


def save_to_gsheets(conn: Any, name: str, action: str, break_minutes: int = 0) -> tuple[bool, str]:
    """Persist attendance changes.

    In demo mode, conn can be None and the function becomes a no-op.

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    if conn is None:
        return True, f"デモモード: {name} さんの{action}表示だけ更新しました"

    now_jst = datetime.now(JST)
    today = now_jst.strftime("%Y-%m-%d")
    time_str = now_jst.strftime("%H:%M")

    try:
        df = conn.read(spreadsheet=URL, worksheet=name, ttl=60)
    except Exception:
        return False, f"{name} のシートが見つかりません"

    if df is None or df.empty:
        df = pd.DataFrame(columns=["日付", "出勤", "退勤", "休憩(分)", "実稼働"])

    for col in ["日付", "出勤", "退勤", "休憩(分)", "実稼働"]:
        if col not in df.columns:
            df[col] = None

    df = df[["日付", "出勤", "退勤", "休憩(分)", "実稼働"]].copy()
    df["日付"] = df["日付"].astype("string")
    df["出勤"] = df["出勤"].astype("string")
    df["退勤"] = df["退勤"].astype("string")
    df["休憩(分)"] = df["休憩(分)"].astype("Int64")
    df["実稼働"] = df["実稼働"].astype("string")

    today_rows = df[df["日付"] == today]

    if action == "退勤" and today_rows.empty:
        return False, "先に出勤を押してください"

    if not today_rows.empty:
        idx = today_rows.index[-1]

        if action == "出勤":
            df.loc[idx, "出勤"] = time_str
        else:
            if pd.notna(df.loc[idx, "退勤"]):
                return False, "すでに退勤済みです"

            df.loc[idx, "退勤"] = time_str
            df.loc[idx, "休憩(分)"] = break_minutes
            df.loc[idx, "実稼働"] = calc_work_duration(
                df.loc[idx, "出勤"],
                df.loc[idx, "退勤"],
                df.loc[idx, "休憩(分)"]
            )
    else:
        new_row = pd.DataFrame([
            {
                "日付": today,
                "出勤": time_str if action == "出勤" else None,
                "退勤": time_str if action == "退勤" else None,
                "休憩(分)": break_minutes if action == "退勤" else None,
                "実稼働": None,
            }
        ])

        new_row["日付"] = new_row["日付"].astype("string")
        new_row["出勤"] = new_row["出勤"].astype("string")
        new_row["退勤"] = new_row["退勤"].astype("string")
        new_row["休憩(分)"] = new_row["休憩(分)"].astype("Int64")
        new_row["実稼働"] = new_row["実稼働"].astype("string")

        df = pd.concat([df, new_row], ignore_index=True)

    out_df = df[["日付", "出勤", "退勤", "休憩(分)", "実稼働"]].copy()
    conn.update(spreadsheet=URL, worksheet=name, data=out_df)
    return True, "保存しました"


def inject_styles(st_module: Any, disp_text: str, clock_col: str) -> None:
    """Inject CSS styles into the Streamlit page."""
    st_module.markdown(
        f"""
<style>
:root {{
  --bg-main: #F7EEF5;
  --bg-sub: #F2E8F5;
  --surface: rgba(255,255,255,0.82);
  --surface-strong: rgba(255,255,255,0.94);
  --line: rgba(223, 208, 241, 0.95);
  --text: #6B6181;
  --text-strong: #5E5674;
  --pink: #F5A8CD;
  --pink-strong: #EC8DBD;
  --purple: #C8B2FF;
  --purple-strong: #AA92F1;
  --yellow: #FFD778;
  --shadow-lg: 0 22px 48px rgba(199, 181, 224, 0.24);
  --shadow-md: 0 12px 26px rgba(199, 181, 224, 0.18);
  --shadow-sm: 0 8px 16px rgba(199, 181, 224, 0.12);
  --inner: inset 0 2px 8px rgba(255,255,255,0.72);
  --grad-main: linear-gradient(90deg, #FFD778 0%, #F5A8CD 48%, #B8A2FF 100%);
}}
.stApp {{
    background:
      radial-gradient(circle at 10% 8%, rgba(255, 205, 229, 0.78), transparent 24%),
      radial-gradient(circle at 88% 14%, rgba(207, 189, 255, 0.78), transparent 22%),
      radial-gradient(circle at 84% 78%, rgba(255, 224, 184, 0.42), transparent 18%),
      linear-gradient(180deg, var(--bg-main) 0%, var(--bg-sub) 52%, #F8EEF6 100%) !important;
    font-family: 'Inter', 'Noto Sans JP', sans-serif;
}}
[data-testid="stAppViewBlockContainer"] {{ max-width: 560px !important; margin: 0 auto; padding-top: 0.8rem !important; }}
[data-testid="stMainBlockContainer"] {{ transform: translateY(-18px); }}
header, footer {{ visibility: hidden !important; }}
* {{ user-select: none !important; -webkit-user-select: none !important; -webkit-tap-highlight-color: transparent !important; }}
html {{ touch-action: manipulation !important; }}
.block-container {{ padding-top: 0.8rem !important; padding-bottom: 2rem !important; }}
div[data-baseweb="select"] > div {{
    background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(247,240,252,0.98) 100%) !important;
    color: var(--text-strong) !important;
    height: 68px !important;
    border-radius: 24px !important;
    border: 1px solid var(--line) !important;
    box-shadow: var(--shadow-md), var(--inner) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}}
div[data-testid="stSelectbox"] div[role="button"] {{
    padding-top: 0 !important; padding-bottom: 0 !important; display: flex !important;
    align-items: center !important; justify-content: center !important; height: 100% !important;
    font-size: 20px !important; font-weight: 500 !important; letter-spacing: 0.04em !important;
}}
div[data-testid="stSelectbox"] input {{ caret-color: transparent !important; cursor: pointer !important; }}
div[data-testid="stSelectbox"], div[data-testid="stSelectbox"] * {{ cursor: pointer !important; }}
.soft-title {{ color: var(--text-strong); text-align: center; letter-spacing: 0.28em; font-size: 21px; margin: 14px 0; font-weight: 600; }}
.balloon-msg {{
    margin: 22px auto 18px; padding: 16px 24px; width: 100%; text-align: center;
    background: linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(247,240,252,0.98) 100%);
    color: var(--text-strong); border-radius: 999px; font-weight: 600; font-size: 17px; position: relative;
    border: 1px solid var(--line); box-shadow: var(--shadow-md), var(--inner); animation: fadeIn 0.35s ease;
}}
.balloon-msg:after {{
    content: ""; position: absolute; top: -10px; left: 50%; margin-left: -9px; width: 18px; height: 18px;
    background: rgba(255,255,255,0.96); border-top: 1px solid var(--line); border-left: 1px solid var(--line); transform: rotate(45deg);
}}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}
div.stButton > button {{
    width: 100% !important; min-width: 100% !important; height: 82px !important;
    background: linear-gradient(#FCF8FD, #FCF8FD) padding-box, linear-gradient(90deg, #FFD778 0%, #F5A8CD 48%, #B8A2FF 100%) border-box !important;
    color: var(--text-strong) !important; font-size: 20px !important; font-weight: 600 !important;
    border: 2px solid transparent !important; border-radius: 26px !important; clip-path: none !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
    box-shadow: var(--shadow-md), var(--inner) !important; transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}
div.stButton > button:hover {{ transform: translateY(-1px) !important; box-shadow: 0 16px 30px rgba(199, 181, 224, 0.22), inset 0 2px 8px rgba(255,255,255,0.72) !important; }}
div.stButton > button:active {{ transform: translateY(0px) scale(0.995) !important; }}
div.stButton {{ width: 100% !important; }}
div.stElementContainer, div.stButton, div.stButton > button {{ width: 100% !important; display: block !important; }}
hr {{ border: none !important; height: 1px !important; background: linear-gradient(90deg, rgba(0,0,0,0), rgba(186,166,213,0.55), rgba(0,0,0,0)) !important; margin: 24px 0 !important; }}
div[data-testid="stExpander"] {{ border-radius: 20px !important; overflow: hidden !important; border: 1px solid var(--line) !important; background: linear-gradient(180deg, rgba(255,255,255,0.8) 0%, rgba(247,240,252,0.96) 100%) !important; box-shadow: var(--shadow-md), var(--inner) !important; }}
div[data-testid="stExpander"] summary {{ font-weight: 600 !important; color: var(--text-strong) !important; }}
div[data-testid="stExpander"] button[kind="secondary"], div[data-testid="stExpander"] button[kind="primary"] {{
    width: 100% !important; height: 50px !important;
    background: linear-gradient(#FCF8FD, #FCF8FD) padding-box, linear-gradient(90deg, #FFD778 0%, #F5A8CD 48%, #B8A2FF 100%) border-box !important;
    color: var(--text-strong) !important; border: 2px solid transparent !important; border-radius: 18px !important; clip-path: none !important;
    margin-top: 10px !important; box-shadow: var(--shadow-sm), var(--inner) !important;
}}
div[data-testid="stExpander"] div[data-baseweb="input"] button {{ clip-path: none !important; border: none !important; height: auto !important; width: auto !important; background: transparent !important; box-shadow: none !important; }}
button[data-baseweb="tab"] {{ border-radius: 999px !important; background: rgba(255,255,255,0.65) !important; color: var(--text-strong) !important; border: 1px solid var(--line) !important; box-shadow: var(--shadow-sm), var(--inner) !important; }}
button[aria-selected="true"][data-baseweb="tab"] {{ background: linear-gradient(90deg, #FFD778 0%, #F5A8CD 48%, #B8A2FF 100%) !important; }}
div[data-baseweb="input"] > div {{ border-radius: 16px !important; border: 1px solid var(--line) !important; background: rgba(255,255,255,0.88) !important; box-shadow: var(--shadow-sm), var(--inner) !important; }}
[data-testid="stStatusWidget"], [data-testid="stDecoration"], [data-testid="stToolbar"], [data-testid="stHeader"], [data-testid="stToast"], .stSpinner {{ display: none !important; }}
st.markdown("""
<style>

/* ===== Streamlit感を消す ===== */
section.main > div {
    padding-top: 0 !important;
}

[data-testid="stVerticalBlock"] > div {
    gap: 0.6rem;
}

/* ===== 全体を1枚の作品にする ===== */
.main-container {
    position: relative;
    padding: 20px;
}

/* ===== ぷくっとしたカード ===== */
.soft-card {
    background: linear-gradient(145deg, #ffffff, #f3eaff);
    border-radius: 30px;
    padding: 20px;
    box-shadow:
        0 20px 40px rgba(200,180,255,0.25),
        inset 0 2px 6px rgba(255,255,255,0.8);
    backdrop-filter: blur(10px);
}

/* ===== 3Dボタン化 ===== */
.stButton > button {
    border-radius: 30px !important;
    background: linear-gradient(145deg, #ffd6ea, #d7c6ff) !important;
    box-shadow:
        0 10px 25px rgba(200,180,255,0.3),
        inset 0 3px 6px rgba(255,255,255,0.9);
    border: none !important;
    font-weight: 600;
    letter-spacing: 0.05em;
}

.stButton > button:active {
    transform: scale(0.96);
}

/* ===== セレクトも立体化 ===== */
div[data-baseweb="select"] > div {
    border-radius: 28px !important;
    background: linear-gradient(145deg, #fff, #f0e7ff) !important;
    box-shadow:
        0 10px 20px rgba(200,180,255,0.25),
        inset 0 2px 6px rgba(255,255,255,0.9);
}

/* ===== 浮遊オブジェ ===== */
.floating {
    position: absolute;
    border-radius: 50%;
    filter: blur(1px);
    opacity: 0.7;
}

.f1 { width: 80px; height: 80px; background:#ffd6ea; top:20px; left:10px;}
.f2 { width: 60px; height: 60px; background:#d7c6ff; top:120px; right:20px;}
.f3 { width: 40px; height: 40px; background:#fff2c6; bottom:20px; left:40px;}


</style>
""",
        unsafe_allow_html=True,
    )

    st_module.components.v1.html(
        f"""
<div id="container" style="width:100%;height:210px;position:relative;overflow:hidden;border-radius:34px;">
  <canvas id="bg" style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:1;"></canvas>
  <canvas id="clk" width="180" height="180" style="position:relative;z-index:2;margin:14px auto 0;display:block;pointer-events:none;"></canvas>
</div>
<script>
const container = document.getElementById('container');
const bg = document.getElementById('bg'); const bctx = bg.getContext('2d');
const clk = document.getElementById('clk'); const cctx = clk.getContext('2d');
let pts = []; let mouse = {{ x: -1000, y: -1000 }};
function res() {{ bg.width = container.offsetWidth; bg.height = container.offsetHeight; }}
container.addEventListener('mousemove', (e) => {{ const rect = container.getBoundingClientRect(); mouse.x = e.clientX - rect.left; mouse.y = e.clientY - rect.top; }});
container.addEventListener('mouseleave', () => {{ mouse.x = -1000; mouse.y = -1000; }});
window.addEventListener('resize', res); res();
const cols = ["#FFD778", "#F5A8CD", "#B8A2FF", "#F3C7DD", "#D7C9FF"];
for(let i=0; i<24; i++) {{ pts.push({{ x: Math.random() * 500, y: Math.random() * 210, vx: (Math.random()-0.5) * 0.25, vy: (Math.random()-0.5) * 0.25, c: cols[Math.floor(Math.random()*cols.length)], s: Math.random() * 5 + 3 }}); }}
function roundedBlob(x, y, r, color) {{ const g = bctx.createRadialGradient(x-r*0.2, y-r*0.2, 2, x, y, r); g.addColorStop(0, 'rgba(255,255,255,0.9)'); g.addColorStop(0.2, color); g.addColorStop(1, color); bctx.fillStyle = g; bctx.beginPath(); bctx.arc(x, y, r, 0, Math.PI*2); bctx.fill(); }}
function drawBgPanel() {{ const g = bctx.createLinearGradient(0, 0, 0, bg.height); g.addColorStop(0, 'rgba(255,255,255,0.42)'); g.addColorStop(1, 'rgba(247,240,252,0.72)'); bctx.fillStyle = g; bctx.beginPath(); const radius = 34; const w = bg.width, h = bg.height; bctx.moveTo(radius, 0); bctx.lineTo(w-radius, 0); bctx.quadraticCurveTo(w, 0, w, radius); bctx.lineTo(w, h-radius); bctx.quadraticCurveTo(w, h, w-radius, h); bctx.lineTo(radius, h); bctx.quadraticCurveTo(0, h, 0, h-radius); bctx.lineTo(0, radius); bctx.quadraticCurveTo(0, 0, radius, 0); bctx.closePath(); bctx.fill(); }}
function draw() {{
  bctx.clearRect(0,0,bg.width,bg.height); drawBgPanel();
  pts.forEach(p => {{ let dx = mouse.x - p.x; let dy = mouse.y - p.y; let dist = Math.sqrt(dx*dx + dy*dy); if(dist < 90 && dist > 0) {{ let force = (90 - dist) / 90; p.x -= dx / dist * force * 2.6; p.y -= dy / dist * force * 2.6; }} p.x += p.vx; p.y += p.vy; if(p.x < 0 || p.x > bg.width) p.vx *= -1; if(p.y < 0 || p.y > bg.height) p.vy *= -1; bctx.globalAlpha = 0.75; roundedBlob(p.x, p.y, p.s, p.c); }});
  cctx.setTransform(1,0,0,1,0,0); cctx.clearRect(0,0,180,180); cctx.translate(90,90); cctx.font = "500 13px Inter, Arial"; cctx.fillStyle = "{clock_col}"; cctx.textAlign = "center";
  for(let n=1; n<=12; n++) {{ cctx.fillText(n, 72*Math.sin(n*Math.PI/6), -72*Math.cos(n*Math.PI/6)+5); }}
  let d = new Date(); let jst = new Date(d.toLocaleString("en-US", {{timeZone: "Asia/Tokyo"}})); let h = jst.getHours()%12, m = jst.getMinutes(), s = jst.getSeconds();
  const hand = (r,l,w,c) => {{ cctx.beginPath(); cctx.lineWidth = w; cctx.lineCap = "round"; cctx.strokeStyle = c; cctx.moveTo(0,0); cctx.rotate(r); cctx.lineTo(0,-l); cctx.stroke(); cctx.rotate(-r); }};
  hand((h*Math.PI/6)+(m*Math.PI/360), 42, 6, "#8A7FB1"); hand(m*Math.PI/30, 62, 4, "#A491D6"); hand(s*Math.PI/30, 70, 2, "#F39DBF");
  cctx.beginPath(); cctx.fillStyle = '#E8DDFF'; cctx.arc(0,0,6,0,Math.PI*2); cctx.fill(); requestAnimationFrame(draw);
}}
draw();
</script>
""",
        height=210,
    )
st.markdown("""
<div class="floating f1"></div>
<div class="floating f2"></div>
<div class="floating f3"></div>
""", unsafe_allow_html=True)

def render_lock_selectbox_typing(st_module: Any) -> None:
    """Prevent typing into the Streamlit select box search input."""
    st_module.components.v1.html(
        """
<script>
(function() {
  const doc = window.parent.document;
  function lockSelectboxTyping() {
    const selectInputs = doc.querySelectorAll('div[data-testid="stSelectbox"] input');
    selectInputs.forEach((input) => {
      input.setAttribute("readonly", "readonly");
      input.setAttribute("inputmode", "none");
      input.setAttribute("autocomplete", "off");
      input.setAttribute("autocorrect", "off");
      input.setAttribute("autocapitalize", "off");
      input.setAttribute("spellcheck", "false");
      input.addEventListener("keydown", (e) => {
        const allowed = ["ArrowUp", "ArrowDown", "Enter", "Escape", "Tab"];
        if (!allowed.includes(e.key)) {
          e.preventDefault();
        }
      });
      input.addEventListener("beforeinput", (e) => { e.preventDefault(); });
      input.addEventListener("input", () => { input.value = ""; });
    });
  }
  lockSelectboxTyping();
  setInterval(lockSelectboxTyping, 500);
})();
</script>
""",
        height=0,
    )


def render_admin_panel(st_module: Any, conn: Any, demo_mode: bool = False) -> None:
    """Render admin tools."""
    st_module.write("---")

    if demo_mode:
        with st_module.expander("🛠 管理者メニュー"):
            st_module.info("デモモードです。管理機能とGoogle Sheets連携は停止しています。")
        return

    with st_module.expander("🛠 管理者メニュー"):
        pw = st_module.text_input("パスワード", type="password")

        if pw == "0123":
            _tab1, tab2 = st_module.tabs(["📊 打刻データ出力", "👥 スタッフ管理"])

            st_module.divider()
            st_module.write("### 📄 税理士提出用ファイルの作成")

            with tab2:
                df_m = conn.read(
                    spreadsheet=URL,
                    worksheet="スタッフ名簿",
                    ttl=60,
                )
                curr_names = df_m["名前"].tolist()

                st_module.markdown("### スタッフの追加")
                new_n = st_module.text_input("新しい名前を入力", key="new_staff_input")

                if st_module.button("新規登録", key="admin_add"):
                    if new_n and new_n not in curr_names:
                        new_staff_df = pd.DataFrame([{"名前": new_n}])
                        updated_df = pd.concat([df_m, new_staff_df], ignore_index=True)
                        conn.update(
                            spreadsheet=URL,
                            worksheet="スタッフ名簿",
                            data=updated_df,
                        )
                        st_module.success(f"{new_n}さんを登録しました")
                        st_module.rerun()

                st_module.divider()
                st_module.markdown("### 登録内容の変更・削除")
                target = st_module.selectbox("対象のスタッフを選択", curr_names)
                renamed = st_module.text_input("名前を修正する", value=target)

                c1_admin, c2_admin = st_module.columns(2)

                with c1_admin:
                    if st_module.button("上書き保存", key="admin_save"):
                        df_m.loc[df_m["名前"] == target, "名前"] = renamed
                        conn.update(
                            spreadsheet=URL,
                            worksheet="スタッフ名簿",
                            data=df_m,
                        )
                        st_module.success("修正しました")
                        st_module.rerun()

                with c2_admin:
                    if "delete_confirm" not in st_module.session_state:
                        st_module.session_state.delete_confirm = False

                    if not st_module.session_state.delete_confirm:
                        if st_module.button("この人を削除", key="admin_del_pre"):
                            st_module.session_state.delete_confirm = True
                            st_module.rerun()
                    else:
                        st_module.warning(f"【確認】本当に {target} さんを消しますか？")
                        col_yes, col_no = st_module.columns(2)
                        with col_yes:
                            if st_module.button("🔴 削除実行", key="admin_del_final"):
                                df_m = df_m[df_m["名前"] != target]
                                conn.update(
                                    spreadsheet=URL,
                                    worksheet="スタッフ名簿",
                                    data=df_m,
                                )
                                st_module.session_state.delete_confirm = False
                                st_module.rerun()
                        with col_no:
                            if st_module.button("キャンセル", key="admin_del_cancel"):
                                st_module.session_state.delete_confirm = False
                                st_module.rerun()


def run_streamlit_app() -> None:
    """Run the Streamlit application."""
    require_streamlit()
    assert st is not None
    assert GSheetsConnection is not None
    assert break_slider is not None

    st.set_page_config(page_title="CRYSTAL TIME CARD", layout="centered")

    theme = get_theme()
    disp_text = str(theme["disp_text"])
    clock_col = str(theme["clock_col"])

    demo_mode = False
    conn = None

    try:
        _secrets = dict(st.secrets["connections"]["gsheets"])
        _secrets["private_key"] = _secrets["private_key"].replace("\n", "\n")
        conn = st.connection("gsheets", type=GSheetsConnection)
        names = read_member_names(conn)
    except Exception:
        demo_mode = True
        names = ["yurika kiriyama", "momo sakura", "hana suzune"]

    inject_styles(st, disp_text, clock_col)

    if demo_mode:
        st.info("デモモードです。見た目確認用のため、Google Sheets連携はオフです。")

    st.markdown('<div class="soft-title">TIME CARD</div>', unsafe_allow_html=True)
    selected_name = st.selectbox("USER", names, label_visibility="collapsed")
    render_lock_selectbox_typing(st)

    if "msg" not in st.session_state:
        st.session_state.msg = "打刻してください"

    selected_break = break_slider(
        label="今日の休憩時間",
        min_value=0,
        max_value=60,
        step=5,
        value=60,
        text_color=disp_text,
        key="break_slider",
    )

    c1, c2 = st.columns(2)
    clicked_action = None
    clicked_msg = None

    with c1:
        if st.button("出 勤", key="in"):
            clicked_action = "出勤"
            clicked_msg = f"✨ {selected_name}さん、おはよう！"

    with c2:
        if st.button("退 勤", key="out"):
            clicked_action = "退勤"
            clicked_msg = f"🌙 {selected_name}さん、お疲れ様！"

    if clicked_msg is not None:
        st.session_state.msg = clicked_msg

    st.markdown(f'<div class="balloon-msg">{st.session_state.msg}</div>', unsafe_allow_html=True)

    if clicked_action is not None:
        success, message = save_to_gsheets(conn, selected_name, clicked_action, selected_break)
        if not success:
            if "すでに退勤済み" in message:
                st.warning(message)
            else:
                st.error(message)

    render_admin_panel(st, conn, demo_mode=demo_mode)


class TimeCardTests(unittest.TestCase):
    """Tests for pure utility logic."""

    def test_calc_work_duration_normal(self) -> None:
        self.assertEqual(calc_work_duration("09:00", "18:00", 60), "08:00")

    def test_calc_work_duration_none_input(self) -> None:
        self.assertIsNone(calc_work_duration(None, "18:00", 60))
        self.assertIsNone(calc_work_duration("09:00", None, 60))

    def test_calc_work_duration_invalid_input(self) -> None:
        self.assertIsNone(calc_work_duration("bad", "18:00", 60))

    def test_calc_work_duration_negative_clamped(self) -> None:
        self.assertEqual(calc_work_duration("18:00", "09:00", 0), "00:00")

    def test_calc_work_duration_nan_break_defaults_to_zero(self) -> None:
        self.assertEqual(calc_work_duration("09:00", "10:00", pd.NA), "01:00")

    def test_get_theme_day(self) -> None:
        theme = get_theme(datetime(2026, 1, 1, 12, 0, tzinfo=JST))
        self.assertFalse(theme["is_night"])
        self.assertEqual(theme["disp_text"], "#6B6181")

    def test_get_theme_night(self) -> None:
        theme = get_theme(datetime(2026, 1, 1, 21, 0, tzinfo=JST))
        self.assertTrue(theme["is_night"])
        self.assertEqual(theme["clock_col"], "#8A7FB1")

    def test_save_to_gsheets_demo_mode(self) -> None:
        success, message = save_to_gsheets(None, "yurika kiriyama", "出勤", 0)
        self.assertTrue(success)
        self.assertIn("デモモード", message)


if __name__ == "__main__":
    if "--test" in sys.argv:
        unittest.main(argv=[sys.argv[0]])
    elif STREAMLIT_AVAILABLE:
        run_streamlit_app()
    else:
        print(
            "Streamlit が見つからないため、アプリは起動しませんでした。\n"
            "依存関係を入れて Streamlit で実行するか、--test でテストを実行してください。"
        )
