# pig_app.py
import streamlit as st
import sqlite3
import pandas as pd
import json
import time
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
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-header"><h1>🐷 猪育种智能助手</h1><p>探索猪基因组 | 辅助科学选配 | 专注畜禽领域</p></div>', unsafe_allow_html=True)

# ---------- 初始化数据库（原有猪只数据库 + 新增历史会话数据库）----------
@st.cache_resource
def init_db():
    # 原有的猪育种数据库
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
    
    # 新增：历史会话数据库
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
    import uuid
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
    # 如果还没标题且是用户第一条消息，自动提取前20字作为标题
    cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
    count = cursor.fetchone()[0]
    if count == 1 and role == "user":
        new_title = content[:20] + ("..." if len(content) > 20 else "")
        rename_session(session_id, new_title)

# ---------- 领域限定的系统提示词 ----------
SYSTEM_PROMPT = """你是一个专业的畜禽育种智能助手，专精于猪、牛、羊、鸡等家畜家禽的遗传育种、基因组选择、繁殖管理和生产性能优化。
你的职责是帮助科研人员和养殖户解决与畜禽育种相关的问题。

【核心原则】
1. 仅回答与畜禽育种、猪遗传、猪生产性能、猪繁殖、猪基因组等相关的问题。
2. 如果用户问的是与畜禽育种完全无关的内容（例如：天气、股票、电影、饮食、健康建议、其他动物如宠物猫狗等），请礼貌拒绝并引导回正题。
3. 回答时要专业、准确，基于科学的育种知识，不要编造数据或提供未经证实的建议。
4. 可以结合用户提供的猪只数据库信息（如品种、日增重、背膘厚等）给出分析建议。
5. 如果问题不明确，可以要求用户补充信息。

【拒绝示例】
- 用户问：“今天天气怎么样？” → 回答：“抱歉，我是畜禽育种助手，无法查询天气信息。请提出与猪育种或畜禽生产相关的问题。”
- 用户问：“如何做红烧肉？” → 回答：“我专注于畜禽育种科研，不涉及烹饪话题。如果您有关于猪的肉质遗传改良方面的问题，我很乐意帮助。”

请记住你的身份，只回答领域内的问题。"""

# ---------- 获取API Key（从secrets或手动） ----------
try:
    # 尝试从 .streamlit/secrets.toml 读取
    api_key = st.secrets["DEEPSEEK_API_KEY"]
    st.success("✅ API Key 已自动从配置文件加载", icon="🔑")
except:
    # 如果读取失败，则在侧边栏显示手动输入框作为备用
    api_key = None
    st.sidebar.warning("未找到预设的 API Key，请在下方手动输入", icon="⚠️")

# ---------- 侧边栏：会话历史 + 配置 ----------
with st.sidebar:
    st.header("📜 对话历史")
    
    # 初始化session_id
    if "current_session_id" not in st.session_state:
        # 获取所有会话，如果没有则创建新会话
        sessions = get_all_sessions()
        if sessions:
            st.session_state.current_session_id = sessions[0][0]
        else:
            st.session_state.current_session_id = create_new_session()
        st.session_state.messages = load_messages(st.session_state.current_session_id)
    
    # 新建对话按钮
    if st.button("➕ 新建对话", use_container_width=True):
        new_id = create_new_session()
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()
    
    # 列出所有会话
    sessions = get_all_sessions()
    for sess_id, title, updated in sessions:
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.button(f"📁 {title[:25]}", key=f"load_{sess_id}", use_container_width=True):
                st.session_state.current_session_id = sess_id
                st.session_state.messages = load_messages(sess_id)
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{sess_id}", help="删除此对话"):
                if sess_id == st.session_state.current_session_id:
                    # 如果删除的是当前会话，先创建新会话再删
                    new_id = create_new_session()
                    st.session_state.current_session_id = new_id
                    st.session_state.messages = []
                delete_session(sess_id)
                st.rerun()
    
    st.divider()
    st.header("⚙️ 智能配置")
    if api_key is None:
        api_key = st.text_input("DeepSeek API Key", type="password", help="输入你的API密钥")
    else:
        st.success("✅ API Key 已从配置文件加载")
    temperature = st.slider("创造性 (Temperature)", 0.0, 1.0, 0.7)
    st.divider()
    st.header("📊 数据总览")
    df = pd.read_sql_query("SELECT breed, COUNT(*) as count FROM pigs GROUP BY breed", conn)
    if not df.empty:
        st.bar_chart(data=df.set_index('breed'))
    else:
        st.info("暂无猪只数据")

# ---------- 查询数据库工具 ----------
def query_database(sql_query):
    try:
        result_df = pd.read_sql_query(sql_query, conn)
        return result_df
    except Exception as e:
        return f"查询出错: {e}"

# ---------- 调用大语言模型（带系统提示词） ----------
def get_llm_response(messages):
    if not api_key:
        return "请先在左侧边栏输入你的 DeepSeek API Key。"
    try:
        # 将系统提示词插入到消息列表开头
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=full_messages,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"抱歉，发生了一点问题：{str(e)}"

# ---------- 聊天界面 ----------
# 显示当前对话历史
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 输入框
if prompt := st.chat_input("🐷 请输入你的问题，例如：查询大白猪的平均日增重？"):
    # 保存用户消息到会话
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.current_session_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 判断是否为数据库查询请求（简单示例，可扩展）
    with st.chat_message("assistant"):
        if "查询" in prompt and ("猪" in prompt or "breed" in prompt or "品种" in prompt):
            # 简单的SQL查询逻辑（可优化）
            # 提取品种关键词
            import re
            breeds = ["大白猪", "长白猪", "杜洛克", "PIC", "大白", "长白", "杜洛克猪"]
            keyword = None
            for b in breeds:
                if b in prompt:
                    keyword = b
                    break
            if keyword:
                sql = f"SELECT * FROM pigs WHERE breed LIKE '%{keyword}%'"
            else:
                # 默认查全部
                sql = "SELECT * FROM pigs LIMIT 10"
            result = query_database(sql)
            if isinstance(result, pd.DataFrame):
                if not result.empty:
                    response = f"📋 查询结果（{keyword or '部分猪只'}）：\n{result.to_markdown()}"
                else:
                    response = "抱歉，没有找到匹配的数据。"
            else:
                response = result
        else:
            # 调用大模型（自动遵循系统提示词的领域限制）
            response = get_llm_response(st.session_state.messages)
        st.markdown(response)
    # 保存助手回复
    st.session_state.messages.append({"role": "assistant", "content": response})
    save_message(st.session_state.current_session_id, "assistant", response)
