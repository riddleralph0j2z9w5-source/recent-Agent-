# pig_app.py
import streamlit as st
import sqlite3
import pandas as pd
import time
import uuid
import requests
from openai import OpenAI
from datetime import datetime

# ---------- 页面样式配置 ----------
st.set_page_config(
    page_title="猪育种智能助手",
    page_icon="🐷",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0.85)),
                    url('https://www.transparenttextures.com/patterns/field.png');
        background-size: cover;
    }
    .main-header {
        color: #4A7A3F;
        text-align: center;
        padding: 1rem;
        background-color: rgba(255, 255, 255, 0.8);
        border-radius: 10px;
        margin-bottom: 2rem;
        border-left: 5px solid #FFA500;
    }
    .st-emotion-cache-1y4p8pa {
        background-color: rgba(240, 248, 235, 0.9);
    }

    /* ===== 侧边栏美化 ===== */
    div[data-testid="stSidebar"] {
        background-color: #fef9e6;
        border-right: 1px solid #e0d5b5;
    }

    div[data-testid="stSidebar"] .stMarkdown h1,
    div[data-testid="stSidebar"] .stMarkdown h2,
    div[data-testid="stSidebar"] .stMarkdown h3 {
        color: #4A7A3F;
        font-weight: 600;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        letter-spacing: 1px;
    }

    /* 新建对话按钮 */
    div[data-testid="stSidebar"] .stButton > button:first-child {
        background-color: #4A7A3F;
        color: white;
        border: none;
        border-radius: 20px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        margin-bottom: 1rem;
        transition: all 0.2s ease;
    }
    div[data-testid="stSidebar"] .stButton > button:first-child:hover {
        background-color: #2c5a2a;
        transform: translateY(-1px);
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    /* 会话项两列布局 */
    div[data-testid="stSidebar"] div[data-testid="column"] {
        align-items: center;
        margin-bottom: 8px;
    }

    /* 会话标题按钮 */
    div[data-testid="stSidebar"] div[data-testid="column"]:first-child .stButton button {
        background-color: #fff9ef;
        border: 1px solid #e2dccd;
        border-radius: 12px;
        color: #3b2e1e;
        font-size: 0.9rem;
        font-weight: normal;
        padding: 0.55rem 0.8rem;
        justify-content: flex-start;
        white-space: normal !important;
        word-break: break-word;
        text-align: left;
        height: auto;
        width: 100%;
        transition: background 0.15s, border-color 0.15s;
    }
    div[data-testid="stSidebar"] div[data-testid="column"]:first-child .stButton button:hover {
        background-color: #f2ebd8;
        border-color: #c7b887;
    }

    /* 功能菜单按钮（第二列） */
    div[data-testid="stSidebar"] div[data-testid="column"]:nth-child(2) .stButton button {
        background-color: transparent;
        border: 1px solid #ddd2b6;
        border-radius: 20px;
        color: #7a6a4e;
        font-size: 1rem;
        padding: 0.45rem 0.2rem;
        transition: all 0.15s;
        width: 100%;
        text-align: center;
    }
    div[data-testid="stSidebar"] div[data-testid="column"]:nth-child(2) .stButton button:hover {
        background-color: #f0e5d2;
        border-color: #b8a77c;
        color: #3b2e1e;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-header"><h1>🐷 猪育种智能助手</h1><p>探索猪基因组 | 辅助科学选配 | 专注畜禽领域</p></div>', unsafe_allow_html=True)

# ---------- 初始化数据库 ----------
@st.cache_resource
def init_db():
    conn = sqlite3.connect('pig_breeding.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pigs (
            pig_id TEXT PRIMARY KEY,
            breed TEXT,
            birth_weight REAL,
            daily_gain REAL,
            backfat_thickness REAL,
            loin_eye_area REAL,
            genetic_markers TEXT,
            sire_id TEXT,
            dam_id TEXT
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM pigs")
    if cursor.fetchone()[0] == 0:
        sample_data = [
            ('P001', '大白猪', 1.52, 850.0, 12.5, 45.0, 'SNP_A, SNP_B', 'S001', 'D001'),
            ('P002', '长白猪', 1.48, 820.0, 11.8, 47.2, 'SNP_A, SNP_C', 'S002', 'D002'),
            ('P003', '杜洛克', 1.60, 900.0, 10.5, 50.1, 'SNP_B, SNP_D', 'S003', 'D003'),
        ]
        cursor.executemany('''
            INSERT INTO pigs (pig_id, breed, birth_weight, daily_gain, backfat_thickness, loin_eye_area, genetic_markers, sire_id, dam_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_data)
        conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
        )
    ''')
    conn.commit()
    return conn

conn = init_db()

# ---------- 会话管理函数 ----------
def get_all_sessions():
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, title, updated_at FROM chat_sessions ORDER BY updated_at DESC")
    return cursor.fetchall()

def create_new_session():
    session_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                   (session_id, "新对话", now, now))
    conn.commit()
    return session_id

def delete_session(session_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    conn.commit()

def rename_session(session_id, new_title):
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                   (new_title, datetime.now().isoformat(), session_id))
    conn.commit()

def load_messages(session_id):
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id", (session_id,))
    return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]

def save_message(session_id, role, content):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                   (session_id, role, content, datetime.now().isoformat()))
    cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                   (datetime.now().isoformat(), session_id))
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
    count = cursor.fetchone()[0]
    if count == 1 and role == "user":
        new_title = content[:20] + ("..." if len(content) > 20 else "")
        rename_session(session_id, new_title)

# ---------- 系统提示词 ----------
SYSTEM_PROMPT = """你是一个专业的畜禽育种智能助手，专精于猪、牛、羊、鸡等家畜家禽的遗传育种、基因组选择、繁殖管理和生产性能优化。
你的职责是帮助科研人员和养殖户解决与畜禽育种相关的问题。

【核心原则】
1. 仅回答与畜禽育种、猪遗传、猪生产性能、猪繁殖、猪基因组等相关的问题。
2. 如果用户问的是与畜禽育种完全无关的内容（例如：天气、股票、电影、饮食、健康建议、其他动物如宠物猫狗等），请礼貌拒绝并引导回正题。
3. 回答时要专业、准确，基于科学的育种知识，不要编造数据或提供未经证实的建议。
4. 可以结合用户提供的猪只数据库信息（如品种、日增重、背膘厚等）给出分析建议。
5. 如果问题不明确，可以要求用户补充信息。

请记住你的身份，只回答领域内的问题。"""

# ---------- 默认 DeepSeek Key（从 secrets 尝试读取）----------
try:
    default_deepseek_key = st.secrets["DEEPSEEK_API_KEY"]
except:
    default_deepseek_key = None

# ---------- 侧边栏：会话历史 + 模型配置 ----------
with st.sidebar:
    st.header("📜 对话历史")

    # 初始化当前会话（可能为 None）
    if "current_session_id" not in st.session_state:
        sessions = get_all_sessions()
        if sessions:
            st.session_state.current_session_id = sessions[0][0]
            st.session_state.messages = load_messages(sessions[0][0])
        else:
            st.session_state.current_session_id = None
            st.session_state.messages = []

    # 新建对话按钮
    if st.button("➕ 新建对话", use_container_width=True):
        new_id = create_new_session()
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()

    # 列出所有会话（两列布局）
    sessions = get_all_sessions()
    for idx, (sess_id, title, updated) in enumerate(sessions):
        display_title = title[:20] + "…" if len(title) > 20 else title
        col1, col2 = st.columns([6, 1])
        with col1:
            if st.button(f"📁 {display_title}", key=f"load_{sess_id}_{idx}", use_container_width=True,
                         help=title if len(title) > 20 else None):
                st.session_state.current_session_id = sess_id
                st.session_state.messages = load_messages(sess_id)
                st.rerun()
        with col2:
            with st.popover("⋮", help="更多操作"):
                # 重命名
                new_title = st.text_input("重命名", value=title, key=f"rename_input_{sess_id}")
                if st.button("保存", key=f"rename_save_{sess_id}"):
                    if new_title.strip():
                        rename_session(sess_id, new_title.strip())
                        st.rerun()
                st.divider()
                # 删除逻辑（支持删除最后一个会话）
                if st.button("删除对话", key=f"del_{sess_id}_{idx}"):
                    other_sessions = [s for s in get_all_sessions() if s[0] != sess_id]
                    if sess_id == st.session_state.current_session_id:
                        if other_sessions:
                            new_id = other_sessions[0][0]
                            st.session_state.current_session_id = new_id
                            st.session_state.messages = load_messages(new_id)
                        else:
                            st.session_state.current_session_id = None
                            st.session_state.messages = []
                    delete_session(sess_id)
                    st.rerun()

    st.divider()
    st.header("⚙️ 智能配置")

    # ---------- 模型选择 ----------
    model_provider = st.selectbox(
        "选择模型",
        ["DeepSeek", "千问 (Qwen)", "文心一言 (ERNIE)", "智谱AI (GLM-4)", "零一万物 (Yi)", "百川智能", "自定义"],
        index=0,
        help="切换不同的大模型，需要提供对应的 API Key。"
    )

    # 根据选择自动填充 base_url 和 model 默认值
    if model_provider == "DeepSeek":
        base_url = "https://api.deepseek.com/v1"
        default_model = "deepseek-chat"
        if default_deepseek_key:
            api_key = default_deepseek_key
            st.success("✅ DeepSeek API Key 已从配置文件加载", icon="🔑")
        else:
            api_key = st.text_input("DeepSeek API Key", type="password", help="输入你的 DeepSeek API Key")
    elif model_provider == "千问 (Qwen)":
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        default_model = "qwen-plus"
        st.info("千问模型需使用阿里云百炼平台的 API Key。")
        api_key = st.text_input("阿里云百炼 API Key", type="password", help="输入你的 DashScope API Key")
    elif model_provider == "文心一言 (ERNIE)":
        base_url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro"
        default_model = "completions_pro"
        st.info("文心一言需要同时提供 API Key 和 Secret Key。")
        api_key = st.text_input("API Key", type="password", help="文心一言的 API Key")
        secret_key = st.text_input("Secret Key", type="password", help="文心一言的 Secret Key")
    elif model_provider == "智谱AI (GLM-4)":
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        default_model = "glm-4-plus"
        st.info("智谱AI 使用 BigModel 平台的 API Key。")
        api_key = st.text_input("智谱 API Key", type="password", help="输入你的 BigModel API Key")
    elif model_provider == "零一万物 (Yi)":
        base_url = "https://api.01.ai/v1"
        default_model = "yi-lightning"
        st.info("零一万物 API 完全兼容 OpenAI。")
        api_key = st.text_input("零一万物 API Key", type="password", help="输入你的零一 API Key")
    elif model_provider == "百川智能":
        base_url = "https://api.baichuan-ai.com/v1"
        default_model = "Baichuan4-Turbo"
        st.info("百川智能模型支持 192K 上下文。")
        api_key = st.text_input("百川 API Key", type="password", help="输入你的百川 API Key")
    else:  # 自定义
        base_url = st.text_input("API Base URL", placeholder="https://api.openai.com/v1")
        default_model = st.text_input("模型名称", placeholder="gpt-3.5-turbo")
        api_key = st.text_input("API Key", type="password", help="输入对应模型的 API Key")
        secret_key = None

    # 温度参数
    temperature = st.slider("创造性 (Temperature)", 0.0, 1.0, 0.7)

    # 将配置保存到 session_state，供后续调用使用
    st.session_state.model_config = {
        "provider": model_provider,
        "base_url": base_url,
        "model_name": default_model,
        "api_key": api_key,
        "secret_key": secret_key if model_provider == "文心一言 (ERNIE)" else None,
        "temperature": temperature,
    }

    st.divider()
    st.header("📊 数据总览")
    df = pd.read_sql_query("SELECT breed, COUNT(*) as count FROM pigs GROUP BY breed", conn)
    if not df.empty:
        st.bar_chart(data=df.set_index('breed'))
    else:
        st.info("暂无猪只数据")

# ---------- 查询数据库 ----------
def query_database(sql_query):
    try:
        result_df = pd.read_sql_query(sql_query, conn)
        return result_df
    except Exception as e:
        return f"查询出错: {e}"

# ---------- 流式调用大模型（支持多个国内模型）----------
def get_llm_response_stream(messages):
    config = st.session_state.get("model_config", {})
    provider = config.get("provider")
    api_key = config.get("api_key")
    secret_key = config.get("secret_key")
    base_url = config.get("base_url")
    model_name = config.get("model_name")
    temperature = config.get("temperature", 0.7)

    # 基本校验
    if not api_key and provider != "文心一言 (ERNIE)":
        yield "❌ 请先在侧边栏配置 API Key。"
        return
    if provider == "文心一言 (ERNIE)" and (not api_key or not secret_key):
        yield "❌ 使用文心一言需要同时提供 API Key 和 Secret Key。"
        return

    try:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        # 文心一言需要先获取 access_token
        if provider == "文心一言 (ERNIE)":
            auth_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
            auth_resp = requests.get(auth_url).json()
            if "access_token" not in auth_resp:
                yield f"文心一言授权失败: {auth_resp.get('error_description', '未知错误')}"
                return
            api_key = auth_resp["access_token"]
            # 文心一言的 base_url 需要使用带 access_token 的完整地址
            full_url = f"{base_url}?access_token={api_key}"
            client = OpenAI(api_key="dummy", base_url=full_url)
        else:
            # 其他模型使用标准 OpenAI 兼容接口
            client = OpenAI(api_key=api_key, base_url=base_url)

        stream = client.chat.completions.create(
            model=model_name,
            messages=full_messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"⚠️ 调用模型时出错：{str(e)}"

# ---------- 聊天界面（支持空状态）----------
if st.session_state.current_session_id is None:
    st.info("👋 暂无对话，请点击左侧「新建对话」开始聊天。")
else:
    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    if prompt := st.chat_input("🐷 请输入你的问题，例如：查询大白猪的平均日增重？"):
        # 保存用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_message(st.session_state.current_session_id, "user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            # 简单判断是否为数据库查询请求
            is_db_query = "查询" in prompt and ("猪" in prompt or "breed" in prompt or "品种" in prompt)

            if is_db_query:
                breeds = ["大白猪", "长白猪", "杜洛克", "PIC"]
                keyword = None
                for b in breeds:
                    if b in prompt:
                        keyword = b
                        break
                sql = f"SELECT * FROM pigs WHERE breed LIKE '%{keyword}%'" if keyword else "SELECT * FROM pigs LIMIT 10"
                result = query_database(sql)
                if isinstance(result, pd.DataFrame) and not result.empty:
                    result_str = f"📋 查询结果（{keyword or '部分猪只'}）：\n{result.to_markdown()}"
                else:
                    result_str = result if isinstance(result, str) else "抱歉，没有找到匹配的数据。"
                for char in result_str:
                    full_response += char
                    message_placeholder.markdown(full_response + "▌")
                    time.sleep(0.02)
                message_placeholder.markdown(full_response)
            else:
                # 调用选择的模型进行对话
                full_response = st.write_stream(get_llm_response_stream(st.session_state.messages), cursor="▌")

            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_message(st.session_state.current_session_id, "assistant", full_response)
