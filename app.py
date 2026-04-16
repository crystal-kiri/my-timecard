import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import os
import io

# ==========================================
# 1. ページ設定と時間判定
# ==========================================
st.set_page_config(page_title="CRYSTAL TIME CARD", layout="centered")

from datetime import timedelta, timezone
JST = timezone(timedelta(hours=+9), 'JST')
now = datetime.now(JST)
is_night = (now.hour >= 17 or now.hour < 8)
MAIN_GRAY = "#454444"

if is_night:
    bg_color, disp_text = "#0a0a0a", "#ffffff"
    box_bg, clock_col = "rgba(255, 255, 255, 0.08)", "#ffffff"
else:
    bg_color, disp_text = "#ffffff", MAIN_GRAY
    box_bg, clock_col = "#f9f9f9", MAIN_GRAY

# --- Google Sheets 接続設定 ---
import streamlit as st
from streamlit_gsheets import GSheetsConnection

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
        color: {MAIN_GRAY} !important;
        height: 64px !important;                   /* 高さを少し微調整 */
        border-radius: 20px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
        
        /* 文字をど真ん中に配置する設定 */
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
        font-size: 20px !important; /* タブレットで見やすいよう少し大きく */
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

    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}

    /* 3. 虹枠ボタン：横幅を強制的に広げる */
    div.stButton > button {{
        width: 100% !important;
        min-width: 100% !important;
        height: 80px !important;
        background-color: transparent !important;
        color: #454444 !important;
        font-size: 20px !important;
        font-weight: 500 !important;
        border: 2px solid !important;
        border-image: linear-gradient(90deg, #ffeb3b, #ff9800, #f44336, #e91e63, #3f51b5) 1 !important;
        
        /* あの「角削り」デザインを復活させつつ横長に対応 */
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

# ==========================================
# 3. 時計＆星セクション (マウスオーバー復活)
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
    
    // マウス座標取得の修正
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
            // マウス回避ロジック
            let dx = mouse.x - p.x; let dy = mouse.y - p.y;
            let dist = Math.sqrt(dx*dx + dy*dy);
            if(dist < 70) {{
                let force = (70 - dist) / 70;
                p.x -= dx / dist * force * 5;
                p.y -= dy / dist * force * 5;
            }}

            p.x += p.vx; p.y += p.vy;
            if(p.x<0 || p.x>bg.width) p.vx*=-1; if(p.y<0 || p.y>bg.height) p.vy*=-1;
            
            bctx.globalAlpha = {0.8 if is_night else 0.4};
            bctx.fillStyle = p.c; bctx.beginPath();
            bctx.arc(p.x, p.y, p.s, 0, Math.PI*2); bctx.fill();
        }});

        // アナログ時計
        cctx.setTransform(1,0,0,1,0,0); cctx.clearRect(0,0,160,160); cctx.translate(80,80);
        cctx.font = "500 13px Arial"; cctx.fillStyle = "{clock_col}"; cctx.textAlign = "center";
        for(let n=1; n<=12; n++) cctx.fillText(n, 65*Math.sin(n*Math.PI/6), -65*Math.cos(n*Math.PI/6)+5);
        
        // --- 修正版：日本時間 ---
        let d = new Date();
        // JavaScriptのブラウザ実行なので、二重中括弧 {{ }} にします
        let jst = new Date(d.toLocaleString("en-US", {{timeZone: "Asia/Tokyo"}}));
        let h=jst.getHours()%12, m=jst.getMinutes(), s=jst.getSeconds();
        // --- ここまで ---

        const hand = (r,l,w,c) => {{ 
            cctx.beginPath(); cctx.lineWidth=w; cctx.lineCap="round"; cctx.strokeStyle=c; 
            cctx.moveTo(0,0); cctx.rotate(r); cctx.lineTo(0,-l); cctx.stroke(); cctx.rotate(-r); 
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
    df_members = conn.read(spreadsheet=URL, worksheet="Sheet2") # Sheet2に名前リストがある想定
    names = df_members['名前'].tolist()
except:
    names = ["スタッフA", "スタッフB"] # 失敗時の予備

st.markdown(f'<div style="color:{disp_text}; text-align:center; letter-spacing:0.2em; font-size:22px; margin:10px 0;">TIME CARD</div>', unsafe_allow_html=True)
selected_name = st.selectbox("USER", names, label_visibility="collapsed")

if 'msg' not in st.session_state: st.session_state.msg = "打刻してください"
st.markdown(f'<div class="balloon-msg">{st.session_state.msg}</div>', unsafe_allow_html=True)

# --- 修正後のコード ---
# 打刻関数
def save_to_gsheets(name, action):
    # 1. 現在のデータを読み込む (ここでURL変数が必要)
    existing_data = conn.read(spreadsheet=URL, worksheet="Sheet1")
    
    # 2. 新しい1行を作る
    from datetime import timezone, timedelta
    jst = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(jst)

    new_entry = pd.DataFrame([{
        "名前": name,
        "日付": now_jst.strftime('%Y-%m-%d'),
        "時刻": now_jst.strftime('%H:%M:%S'),
        "区分": action
    }])
    
    # 3. 既存のデータと合体させる
    updated_df = pd.concat([existing_data, new_entry], ignore_index=True)
    
    # 4. シート全体を最新状態で上書きする
    conn.update(spreadsheet=URL, worksheet="Sheet1", data=updated_df)

c1, c2 = st.columns(2)
with c1:
    if st.button("出 勤", key="in"):
        save_to_gsheets(selected_name, "出勤")
        st.session_state.msg = f"✨ {selected_name}さん、おはよう！"
        st.rerun()

with c2:
    if st.button("退 勤", key="out"):
        save_to_gsheets(selected_name, "退勤")
        st.session_state.msg = f"🌙 {selected_name}さん、お疲れ様！"
        st.rerun()

# ==========================================
# 5. 管理者ツール
# ==========================================
st.write("---")
with st.expander("🛠 管理者メニュー"):
    pw = st.text_input("パスワード", type="password")
    if pw == "0123":
        tab1, tab2 = st.tabs(["📊 打刻データ出力", "👥 スタッフ管理"])

        # --- タブ1: ログ表示と税理士提出用Excel出力 ---
        
        with tab1:
            if os.path.exists(LOG_FILE):
                df_l = pd.read_csv(LOG_FILE, encoding="utf_8_sig")
                st.write("### ログ一覧")
                st.dataframe(df_l.sort_index(ascending=False), use_container_width=True)

                st.divider()
                st.write("### 📄 税理士提出用ファイルの作成")
                
                today = datetime.now()
                target_year = st.number_input("年", value=today.year)
                # 月を「3」や「03」どちらでも対応できるように準備
                target_month_int = st.selectbox("月", range(1, 13), index=today.month-1)

                if st.button("Excelファイルを作成する", key="make_excel"):
                    # 1. データのコピーを作成して日付を「日付型」に強制変換
                    df_month = df_l.copy()
                    df_month['日付'] = pd.to_datetime(df_month['日付'])
                    
                    # 2. 指定された年と月でフィルタリング
                    df_month = df_month[
                        (df_month['日付'].dt.year == target_year) & 
                        (df_month['日付'].dt.month == target_month_int)
                    ]
                    
                    if df_month.empty:
                        st.warning(f"{target_year}年{target_month_int}月のデータが見つかりませんでした。")
                    else:
                        output = io.BytesIO()
                        # 【重要】xlsxwriterを使わず、openpyxlを指定
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            
                            for name in df_month['名前'].unique():
                                df_staff = df_month[df_month['名前'] == name].copy()
                                
                                # 時刻を文字列にする（Excelで変な変換をされないよう）
                                report = df_staff.pivot_table(
                                    index='日付', 
                                    columns='区分', 
                                    values='時刻', 
                                    aggfunc='last'
                                ).reset_index()
                                
                                # 列の補完
                                if '出勤' not in report.columns: report['出勤'] = ""
                                if '退勤' not in report.columns: report['退勤'] = ""
                                
                                # 曜日・月・日の作成
                                report['曜日'] = report['日付'].dt.day_name().map({
                                    'Monday': '月', 'Tuesday': '火', 'Wednesday': '水', 
                                    'Thursday': '木', 'Friday': '金', 'Saturday': '土', 'Sunday': '日'
                                })
                                report['月'] = report['日付'].dt.month
                                report['日'] = report['日付'].dt.day
                                
                                # 並び替え
                                final = report[['月', '日', '曜日', '出勤', '退勤']]
                                final.columns = ['月', '日', '曜日', '始業時刻', '終業時刻']
                                
                                # 書き出し
                                final.to_excel(writer, sheet_name=str(name)[:31], index=False)
                            
                        st.success(f"✨ {target_month_int}月分のExcelを作成しました！")
                        st.download_button(
                            label="📥 Excelをダウンロード",
                            data=output.getvalue(),
                            file_name=f"給与計算_{target_year}_{target_month_int}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            else:
                st.info("データがありません。")

        with tab2:
            df_m = pd.read_csv(USER_FILE)
            curr_names = df_m['名前'].tolist()

            st.markdown("### スタッフの追加")
            new_n = st.text_input("新しい名前を入力", key="new_staff_input")
            if st.button("新規登録", key="admin_add"):
                if new_n and new_n not in curr_names:
                    new_df = pd.concat([df_m, pd.DataFrame([{'名前': new_n}])], ignore_index=True)
                    new_df.to_csv(USER_FILE, index=False, encoding="utf_8_sig")
                    st.success(f"{new_n}さんを登録しました")
                    st.rerun()

            st.divider()

            st.markdown("### 登録内容の変更・削除")
            target = st.selectbox("対象のスタッフを選択", curr_names)
            renamed = st.text_input("名前を修正する", value=target)
            
            # --- ボタンを横に並べる ---
            c1, c2 = st.columns(2)
            with c1:
                if st.button("上書き保存", key="admin_save"):
                    df_m.loc[df_m['名前'] == target, '名前'] = renamed
                    df_m.to_csv(USER_FILE, index=False, encoding="utf_8_sig")
                    st.success("修正しました")
                    st.rerun()
            
            with c2:
                # 削除の2段階ガード
                if "delete_confirm" not in st.session_state:
                    st.session_state.delete_confirm = False

                if not st.session_state.delete_confirm:
                    if st.button("この人を削除", key="admin_del_pre"):
                        st.session_state.delete_confirm = True
                        st.rerun()
                else:
                    # 1回押すとこっちに切り替わる
                    st.warning(f"【確認】本当に {target} さんを消しますか？")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("🔴 削除実行", key="admin_del_final"):
                            df_m = df_m[df_m['名前'] != target]
                            df_m.to_csv(USER_FILE, index=False, encoding="utf_8_sig")
                            st.session_state.delete_confirm = False
                            st.rerun()
                    with col_no:
                        if st.button("キャンセル", key="admin_del_cancel"):
                            st.session_state.delete_confirm = False
                            st.rerun()

    # 管理画面のボタンも「虹枠」にするためのCSS（微調整版）
    # 管理画面のボタンデザインを整えつつ、パスワード欄などのシステムボタンは除外する
    st.markdown("""
        <style>
        /* 管理画面内の「操作用ボタン」だけに限定して虹枠を適用 */
        div[data-testid="stExpander"] button[kind="secondary"],
        div[data-testid="stExpander"] button[kind="primary"] {
            width: 100% !important;
            height: 50px !important;
            background-color: transparent !important;
            font-size: 16_px !important;
            border: 1px solid !important;
            border-image: linear-gradient(90deg, #ffeb3b, #ff9800, #f44336, #e91e63, #3f51b5) 1 !important;
            clip-path: polygon(10px 0%, calc(100% - 10px) 0%, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0% calc(100% - 10px), 0% 10px) !important;
            margin-top: 10px !important;
        }

        /* パスワード欄の中の「目」のアイコンボタンなどは虹枠にしない（リセット） */
        div[data-testid="stExpander"] div[data-baseweb="input"] button {
            clip-path: none !important;
            border: none !important;
            border-image: none !important;
            height: auto !important;
            width: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)
