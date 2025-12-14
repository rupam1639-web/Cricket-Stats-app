import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import requests
from duckduckgo_search import DDGS
import wikipedia
import google.generativeai as genai
import json

# --- CONFIGURATION ---
st.set_page_config(page_title="Cricket Stats Hub", page_icon="🏏", layout="wide")

# ==========================================
# 🔑 PASTE KEYS HERE
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
MONGO_URI = "mongodb+srv://rupam1639_db_user:Rupam%402007@cluster0.zgnf6pz.mongodb.net/?appName=Cluster0" 
# ==========================================

genai.configure(api_key=GEMINI_API_KEY)

# DB Setup
try:
    client = MongoClient(MONGO_URI)
    db = client['cricket_db']
    collection = db['search_history']
    db_status = "✅ DB Connected"
except:
    db_status = "⚠️ DB Offline"

# --- PART 1: LIVE SCRAPING (PREFERED) ---
def get_cricbuzz_url(player_name):
    """Try to find URL via DuckDuckGo"""
    try:
        results = DDGS().text(f"{player_name} cricbuzz profile", max_results=3)
        for r in results:
            if "cricbuzz.com/profiles/" in r['href']:
                url = r['href']
                return url + "/stats" if not url.endswith("/stats") else url
        return None
    except:
        return None

def get_live_stats(url):
    """Try to read table using Pandas"""
    try:
        header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=header, timeout=5)
        
        # Read all tables
        dfs = pd.read_html(response.text)
        
        # Find the Batting Table (contains 'Runs' and 'ODI' or 'Test')
        for df in dfs:
            s = df.to_string().lower()
            if "runs" in s and ("odi" in s or "test" in s):
                return df
        return None
    except:
        return None

# --- PART 2: AI BACKUP (IF SCRAPING FAILS) ---
def get_ai_stats(player_name):
    """Fallback: Ask Gemini to generate the table data"""
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = f"""
    Generate a cricket career stats table for {player_name}.
    Return JSON with keys: "matches", "innings", "runs", "average", "wickets".
    Format as a list of objects for "Test", "ODI", "T20I".
    Example:
    [
      {{"Format": "Test", "Matches": 100, "Runs": 5000, "Average": 50.0}},
      {{"Format": "ODI", "Matches": 200, "Runs": 10000, "Average": 58.0}}
    ]
    Strict JSON only. No markdown.
    """
    try:
        res = model.generate_content(prompt)
        text = res.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return pd.DataFrame(data)
    except:
        return None

# --- HELPER: IMAGE ---
def get_image(player_name):
    try:
        page = wikipedia.page(player_name, auto_suggest=False)
        for img in page.images:
            if img.lower().endswith(('.jpg', '.png')) and "svg" not in img.lower():
                return img
        return "https://placehold.co/200x200?text=No+Img"
    except:
        return "https://placehold.co/200x200?text=No+Img"

# --- UI LOGIC ---
st.title("🏏 Smart Cricket Analyzer")
st.markdown(f"**System Status:** {db_status}")

col1, col2 = st.columns([3, 1])
with col1:
    player = st.text_input("Enter Player Name", placeholder="e.g. Virat Kohli")
with col2:
    st.write("") 
    st.write("") 
    btn = st.button("Analyze 🚀", use_container_width=True)

if btn and player:
    with st.spinner(f"Searching data sources for {player}..."):
        
        # Initialize variables
        stats_df = None
        source_label = "Unknown"
        profile_url = None
        
        # STEP 1: Try Live Scraping
        profile_url = get_cricbuzz_url(player)
        if profile_url:
            stats_df = get_live_stats(profile_url)
            if stats_df is not None:
                source_label = "Live Cricbuzz Data 🔴"
        
        # STEP 2: If Scraping failed, use AI
        if stats_df is None:
            stats_df = get_ai_stats(player)
            source_label = "AI Generated (Backup) 🤖"

        # STEP 3: Get Image
        img_url = get_image(player)

        # STEP 4: Display
        if stats_df is not None:
            # Save to DB
            if 'collection' in globals():
                collection.insert_one({
                    "query": player, 
                    "timestamp": datetime.now(), 
                    "source": source_label
                })

            # Header
            c1, c2 = st.columns([1, 4])
            with c1:
                st.image(img_url, width=150)
            with c2:
                st.header(player.title())
                if "Live" in source_label:
                    st.success(f"Source: {source_label}")
                else:
                    st.warning(f"Source: {source_label} (Live search blocked/failed)")
            
            st.subheader("📊 Career Performance")
            st.table(stats_df)
        else:
            st.error("System Failure: Both Live Search and AI Backup failed. Please check your internet or API Key.")

# --- HISTORY ---
st.sidebar.header("Log")
if st.sidebar.button("Refresh"):
    if 'collection' in globals():
        items = list(collection.find().sort("timestamp", -1).limit(5))
        for i in items:
            st.sidebar.caption(f"{i['query']} - {i.get('source', 'Unknown')}")