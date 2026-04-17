import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from streamlit_gsheets import GSheetsConnection
import os
import io

# ==========================================
# 1. ページ設定と時間判定
# ==========================================
st.set_page_config(page_title="CRYSTAL TIME CARD", layout="centered")

JST = timezone(timedelta(hours=+9), 'JST')
now = datetime.now(JST)
is_night = (now.hour >= 17 or now.hour < 8)
MAIN_GRAY = "#454444"

if is_night:
    bg_color = "#605D86"      # 深いネイビー
    disp_text = "#FDFBF9"     # 少し柔らかい白（真っ白より目に優しい）
    box_bg = "rgba(255, 255, 255, 0.06)"
    clock_col = "#e6eaf2"
else:
    bg_color = "#ffffff"
    disp_text = "#454444"
    box_bg = "#f9f9f9"
    clock_col = "#454444"

# --- Google Sheets 接続設定 ---
secrets = dict(st.secrets["connections"]["gsheets"])
secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")

conn = st.connection("gsheets", type=GSheetsConnection)
URL = "https://docs.google.com/spreadsheets/d/1muQ7GR7RbVtOBYS3nV-xy7VCq66QqE04TqFxZo5ndtg/edit?gid=643044008#gid=643044008"

# ==========================================
# 2. CSSデザイン (ボタン・メッセージ・全体)
# ==========================================
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500&display=swap');

    /* 基本背景とコンテナ */
    .stApp {{
        background-color: {bg_color} !important;
        font-family: 'Noto Sans JP', sans-serif;
    }}

    [data-testid="stAppViewBlockContainer"] {{
        max-width: 500px !important;
        margin: 0 auto;
    }}

    header, footer {{ visibility: hidden !important; }}

    /* タブレット誤操作防止 */
    * {{
        user-select: none !important;
        -webkit-user-select: none !important;
        -webkit-tap-highlight-color: transparent !important;
    }}
    html {{ touch-action: manipulation !important; }}

    /* 1. 氏名選択の枠を「ころんと白く」＆「ど真ん中」 */
    div[data-baseweb="select"] > div {{
        background-color: #ffffff !important;
        color: #371637 !important;
        height: 64px !important;
        border-radius: 20px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;

        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}

    /* 選択中のテキスト自体の位置調整 */
    div[data-testid="stSelectbox"] div[role="button"] {{
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 100% !important;
        font-size: 20px !important;
        font-weight: 500 !important;
    }}

    /* 2. 吹き出し：白くてころんとしたデザイン */
    .balloon-msg {{
        margin: 20px auto;
        padding: 15px 25px;
        width: 100%;
        text-align: center;
        background-color: #ffffff;
        color: {MAIN_GRAY};
        border-radius: 30px;
        font-weight: 500;
        font-size: 17px;
        position: relative;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        animation: fadeIn 0.4s ease;
    }}

    .balloon-msg:after {{
        content: "";
        position: absolute;
        top: -12px;
        left: 50%;
        margin-left: -10px;
        border-bottom: 12px solid #ffffff;
        border-left: 10px solid transparent;
        border-right: 10px solid transparent;
    }}

    @keyframes fadeIn {{
        from {{ opacity: 0; transform: translateY(5px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* 3. 虹枠ボタン：横幅を強制的に広げる */
    div.stButton > button {{
        width: 100% !important;
        min-width: 100% !important;
        height: 80px !important;
        background-color: transparent !important;
        color: {disp_text} !important;
        font-size: 20px !important;
        font-weight: 500 !important;
        border: 1px solid !important;
        border-image: linear-gradient(90deg, #ffeb3b, #ff9800, #f44336, #e91e63, #3f51b5) 1 !important;

        clip-path: polygon(15px 0%, calc(100% - 15px) 0%, 100% 15px, 100% calc(100% - 15px), calc(100% - 15px) 100%, 15px 100%, 0% calc(100% - 15px), 0% 15px) !important;

        border-radius: 0px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}

    /* ボタンの親要素も横いっぱいに広げる */
    div.stButton {{
        width: 100% !important;
    }}
    div.stElementContainer, div.stButton, div.stButton > button {{
        width: 100% !important;
        display: block !important;
    }}
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
<style>
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToast"] { display: none !important; }
.stSpinner { display: none !important; }

/* ===== 休憩スライダー ===== */

div[data-testid="stSlider"] [data-baseweb="slider"] > div {
    background: linear-gradient(90deg,
        rgba(255,235,59,0.85),
        rgba(255,152,0,0.85),
        rgba(244,67,54,0.85),
        rgba(233,30,99,0.85),
        rgba(63,81,181,0.85)
    ) !important;
    border-radius: 999px !important;
    height: 6px !important;
}

div[data-testid="stSlider"] div[role="slider"] {
    background: #ffffff !important;
    border: 3px solid #e91e63 !important;
    box-shadow: 0 0 10px rgba(233, 30, 99, 0.35) !important;
}
</style>
""", unsafe_allow_html=True)
# ==========================================
# 3. 時計＆星セクション
# ==========================================
st.components.v1.html(f"""
    <div id="container" style="width: 100%; height: 180px; position: relative; overflow: hidden; border-radius:20px; cursor: crosshair;">
        <canvas id="bg" style="position: absolute; top:0; left:0; width:100%; height:100%; z-index:1;"></canvas>
        <canvas id="clk" width="160" height="160" style="position: relative; z-index:2; margin: 0 auto; display: block; pointer-events: none;"></canvas>
    </div>
    <script>
    const container = document.getElementById('container');
    const bg = document.getElementById('bg'); const bctx = bg.getContext('2d');
    const clk = document.getElementById('clk'); const cctx = clk.getContext('2d');
    let pts = []; let mouse = {{ x: -1000, y: -1000 }};

    function res() {{ bg.width = container.offsetWidth; bg.height = container.offsetHeight; }}

    container.addEventListener('mousemove', (e) => {{
        const rect = container.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
    }});
    container.addEventListener('mouseleave', () => {{ mouse.x = -1000; mouse.y = -1000; }});

    window.addEventListener('resize', res); res();

    const cols = ["#ffeb3b","#ff9800","#f44336","#e91e63","#3f51b5"];
    for(let i=0; i<30; i++) {{
        pts.push({{
            x: Math.random() * 500, y: Math.random() * 180,
            vx: (Math.random()-0.5) * 0.4, vy: (Math.random()-0.5) * 0.4,
            c: cols[Math.floor(Math.random()*5)], s: Math.random() * 2 + 1
        }});
    }}

    function draw() {{
        bctx.clearRect(0,0,bg.width,bg.height);
        pts.forEach(p => {{
            let dx = mouse.x - p.x; let dy = mouse.y - p.y;
            let dist = Math.sqrt(dx*dx + dy*dy);
            if(dist < 70 && dist > 0) {{
                let force = (70 - dist) / 70;
                p.x -= dx / dist * force * 5;
                p.y -= dy / dist * force * 5;
            }}

            p.x += p.vx; p.y += p.vy;
            if(p.x < 0 || p.x > bg.width) p.vx *= -1;
            if(p.y < 0 || p.y > bg.height) p.vy *= -1;

            bctx.globalAlpha = {0.8 if is_night else 0.4};
            bctx.fillStyle = p.c;
            bctx.beginPath();
            bctx.arc(p.x, p.y, p.s, 0, Math.PI*2);
            bctx.fill();
        }});

        cctx.setTransform(1,0,0,1,0,0);
        cctx.clearRect(0,0,160,160);
        cctx.translate(80,80);
        cctx.font = "500 13px Arial";
        cctx.fillStyle = "{clock_col}";
        cctx.textAlign = "center";

        for(let n=1; n<=12; n++) {{
            cctx.fillText(n, 65*Math.sin(n*Math.PI/6), -65*Math.cos(n*Math.PI/6)+5);
        }}

        let d = new Date();
        let jst = new Date(d.toLocaleString("en-US", {{timeZone: "Asia/Tokyo"}}));
        let h = jst.getHours()%12, m = jst.getMinutes(), s = jst.getSeconds();

        const hand = (r,l,w,c) => {{
            cctx.beginPath();
            cctx.lineWidth = w;
            cctx.lineCap = "round";
            cctx.strokeStyle = c;
            cctx.moveTo(0,0);
            cctx.rotate(r);
            cctx.lineTo(0,-l);
            cctx.stroke();
            cctx.rotate(-r);
        }};

        hand((h*Math.PI/6)+(m*Math.PI/360), 40, 5, "{clock_col}");
        hand(m*Math.PI/30, 60, 3, "{clock_col}");
        hand(s*Math.PI/30, 70, 1.2, "#f44336");

        requestAnimationFrame(draw);
    }}
    draw();
    </script>
""", height=180)

# ==========================================
# 4. 操作セクション
# ==========================================
try:
    df_members = conn.read(spreadsheet=URL, worksheet="スタッフ名簿", ttl=0)

    if df_members is None or df_members.empty or "名前" not in df_members.columns:
        st.error("スタッフ名簿が空か、名前列がありません")
        st.stop()

    names = (
        df_members["名前"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    if not names:
        st.error("スタッフ名簿に名前がありません")
        st.stop()

except Exception as e:
    st.error(f"スタッフ名簿の読み込みに失敗しました: {e}")
    st.stop()

st.markdown(
    f'<div style="color:{disp_text}; text-align:center; letter-spacing:0.2em; font-size:22px; margin:10px 0;">TIME CARD</div>',
    unsafe_allow_html=True
)

selected_name = st.selectbox("USER", names, label_visibility="collapsed")

if 'msg' not in st.session_state:
    st.session_state.msg = "打刻してください"
def save_to_gsheets(name, action, break_minutes=0):
    now_jst = datetime.now(JST)
    today = now_jst.strftime('%Y-%m-%d')
    time_str = now_jst.strftime('%H:%M:%S')

    try:
        df = conn.read(spreadsheet=URL, worksheet=name, ttl=0)
    except Exception:
        st.error(f"{name} のシートが見つかりません")
        return

    if df is None or df.empty:
        df = pd.DataFrame(columns=["日付", "出勤", "退勤", "休憩(分)"])

    for col in ["日付", "出勤", "退勤", "休憩(分)"]:
        if col not in df.columns:
            df[col] = None

    df = df[["日付", "出勤", "退勤", "休憩(分)"]].copy()
    df["日付"] = df["日付"].astype("string")
    df["出勤"] = df["出勤"].astype("string")
    df["退勤"] = df["退勤"].astype("string")
    df["休憩(分)"] = df["休憩(分)"].astype("Int64")

    today_rows = df[df["日付"] == today]
    if action == "退勤" and today_rows.empty:
        st.error("先に出勤を押してください")
        return

    if not today_rows.empty:
        idx = today_rows.index[-1]
        if action == "出勤":
            df.loc[idx, "出勤"] = time_str
        else:
            if pd.notna(df.loc[idx, "退勤"]):
                st.warning("すでに退勤済みです")
                return
            df.loc[idx, "退勤"] = time_str
            df.loc[idx, "休憩(分)"] = break_minutes
    else:
        new_row = pd.DataFrame([{
            "日付": today,
            "出勤": time_str if action == "出勤" else None,
            "退勤": time_str if action == "退勤" else None,
            "休憩(分)": break_minutes if action == "退勤" else None
        }])

        new_row["日付"] = new_row["日付"].astype("string")
        new_row["出勤"] = new_row["出勤"].astype("string")
        new_row["退勤"] = new_row["退勤"].astype("string")
        new_row["休憩(分)"] = new_row["休憩(分)"].astype("Int64")

        df = pd.concat([df, new_row], ignore_index=True)

    out_df = df[["日付", "出勤", "退勤", "休憩(分)"]].copy()
    conn.update(spreadsheet=URL, worksheet=name, data=out_df)

selected_break = st.slider(
    "今日の休憩時間",
    min_value=0,
    max_value=60,
    step=5,
    value=60
)

if selected_break == 0:
    st.caption("休憩なし")
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
    save_to_gsheets(selected_name, clicked_action, selected_break)
# ==========================================
# 5. 管理者ツール
# ==========================================
st.write("---")

with st.expander("🛠 管理者メニュー"):
    pw = st.text_input("パスワード", type="password")

    if pw == "0123":
        tab1, tab2 = st.tabs(["📊 打刻データ出力", "👥 スタッフ管理"])

        st.divider()
        st.write("### 📄 税理士提出用ファイルの作成")

        with tab2:
            df_m = conn.read(
                spreadsheet=URL,
                worksheet="スタッフ名簿",
                ttl=0
            )
            curr_names = df_m['名前'].tolist()

            st.markdown("### スタッフの追加")
            new_n = st.text_input("新しい名前を入力", key="new_staff_input")

            if st.button("新規登録", key="admin_add"):
                if new_n and new_n not in curr_names:
                    new_staff_df = pd.DataFrame([{'名前': new_n}])
                    updated_df = pd.concat([df_m, new_staff_df], ignore_index=True)

                    conn.update(
                        spreadsheet=URL,
                        worksheet="スタッフ名簿",
                        data=updated_df
                    )

                    st.success(f"{new_n}さんを登録しました")
                    st.rerun()

            st.divider()

            st.markdown("### 登録内容の変更・削除")
            target = st.selectbox("対象のスタッフを選択", curr_names)
            renamed = st.text_input("名前を修正する", value=target)

            c1_admin, c2_admin = st.columns(2)

            with c1_admin:
                if st.button("上書き保存", key="admin_save"):
                    df_m.loc[df_m['名前'] == target, '名前'] = renamed
                    conn.update(
                        spreadsheet=URL,
                        worksheet="スタッフ名簿",
                        data=df_m
                    )
                    st.success("修正しました")
                    st.rerun()

            with c2_admin:
                if "delete_confirm" not in st.session_state:
                    st.session_state.delete_confirm = False

                if not st.session_state.delete_confirm:
                    if st.button("この人を削除", key="admin_del_pre"):
                        st.session_state.delete_confirm = True
                        st.rerun()
                else:
                    st.warning(f"【確認】本当に {target} さんを消しますか？")

                    col_yes, col_no = st.columns(2)

                    with col_yes:
                        if st.button("🔴 削除実行", key="admin_del_final"):
                            df_m = df_m[df_m['名前'] != target]
                            conn.update(
                                spreadsheet=URL,
                                worksheet="スタッフ名簿",
                                data=df_m
                            )
                            st.session_state.delete_confirm = False
                            st.rerun()

                    with col_no:
                        if st.button("キャンセル", key="admin_del_cancel"):
                            st.session_state.delete_confirm = False
                            st.rerun()
expander_css = """
<style>
div[data-testid="stExpander"] button[kind="secondary"],
div[data-testid="stExpander"] button[kind="primary"] {
    width: 100% !important;
    height: 50px !important;
    background-color: transparent !important;
    font-size: 16px !important;
    border: 1px solid !important;
    border-image: linear-gradient(90deg, #ffeb3b, #ff9800, #f44336, #e91e63, #3f51b5) 1 !important;
    clip-path: polygon(10px 0%, calc(100% - 10px) 0%, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0% calc(100% - 10px), 0% 10px) !important;
    margin-top: 10px !important;
}

div[data-testid="stExpander"] div[data-baseweb="input"] button {
    clip-path: none !important;
    border: none !important;
    border-image: none !important;
    height: auto !important;
    width: auto !important;
}
</style>
"""

st.markdown(expander_css, unsafe_allow_html=True)
