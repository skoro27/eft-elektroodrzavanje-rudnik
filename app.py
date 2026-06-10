import streamlit as st
import sqlite3
import pandas as pd
import re
from groq import Groq
import os

st.set_page_config(page_title="Elektro Održavanje - Rudnik", layout="wide")
st.title("⚡ Elektro Održavanje - Rudnik")
st.caption("Analiza potrošnje energije pomoću Groq AI")

# API ključ iz Render Environment Variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ========== SIDEBAR ==========
with st.sidebar:
    st.header("📊 Podaci")
    uploaded_file = st.file_uploader(
        "Upload podataka (CSV, Excel, .db, .sql)",
        type=["csv", "xlsx", "xls", "db", "sql", "sqlite", "sqlite3"]
    )
    
    if uploaded_file:
        file_content = uploaded_file.read()
        
        try:
            conn = sqlite3.connect("baza.db")
            
            if uploaded_file.name.endswith('.csv'):
                # CSV fajl - pročitaj i kreiraj tabelu
                df = pd.read_csv(uploaded_file)
                df.to_sql('podaci', conn, if_exists='replace', index=False)
                st.success(f"✅ CSV učitana! ({len(df)} redova, {len(df.columns)} kolona)")
                
            elif uploaded_file.name.endswith(('.xlsx', '.xls')):
                # Excel fajl
                df = pd.read_excel(uploaded_file)
                df.to_sql('podaci', conn, if_exists='replace', index=False)
                st.success(f"✅ Excel učitana! ({len(df)} redova, {len(df.columns)} kolona)")
                
            elif uploaded_file.name.endswith('.sql'):
                # SQL fajl
                with open("baza.sql", "w", encoding="utf-8") as f:
                    f.write(file_content.decode("utf-8", errors="ignore"))
                
                cursor = conn.cursor()
                sql_text = file_content.decode("utf-8", errors="ignore")
                sql_text = re.sub(r'--.*', '', sql_text)
                sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)
                sql_text = re.sub(r'ENGINE=\w+', '', sql_text)
                sql_text = re.sub(r'AUTO_INCREMENT=\d+', '', sql_text)
                sql_text = re.sub(r'DEFAULT CHARSET=\w+', '', sql_text)
                sql_text = re.sub(r'COLLATE=\w+', '', sql_text)
                sql_text = re.sub(r'`', '"', sql_text)
                
                statements = [s.strip() for s in sql_text.split(';') if s.strip()]
                for statement in statements:
                    if statement.upper().startswith(('CREATE', 'INSERT', 'ALTER', 'DROP')):
                        try:
                            cursor.execute(statement)
                        except:
                            pass
                conn.commit()
                st.success("✅ SQL fajl učitana!")
                
            else:
                # .db fajl
                with open("baza.db", "wb") as f:
                    f.write(file_content)
                st.success("✅ Baza učitana!")
            
            conn.close()
            
        except Exception as e:
            st.error(f"Greška pri učitavanju: {str(e)}")
    
    st.divider()
    
    if GROQ_API_KEY:
        st.success("🔑 API ključ podešen")
    else:
        st.error("⚠️ API ključ nije podešen!")

# ========== GLAVNI DIO ==========

pitanje = st.text_area(
    "💬 Postavite pitanje o potrošnji energije:",
    height=100,
    placeholder="Npr: Kolika je ukupna potrošnja za juli? Koja etaža troši najviše?"
)

if st.button("🔍 Analiziraj", type="primary", use_container_width=True):
    if not uploaded_file:
        st.warning("⚠️ Prvo upload-ujte fajl")
    elif not GROQ_API_KEY:
        st.warning("⚠️ API ključ nije podešen")
    elif not pitanje.strip():
        st.warning("⚠️ Unesite pitanje")
    else:
        try:
            with st.spinner("🧠 AI analizira podatke..."):
                conn = sqlite3.connect("baza.db")
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tabele = [row[0] for row in cursor.fetchall()]
                
                if not tabele:
                    st.error("❌ Nema tabela u bazi!")
                    st.stop()
                
                prva_tabela = tabele[0]
                cursor.execute(f"SELECT * FROM `{prva_tabela}` LIMIT 5")
                kolone = [desc[0] for desc in cursor.description]
                redovi = cursor.fetchall()
                ukupno = cursor.execute(f"SELECT COUNT(*) FROM `{prva_tabela}`").fetchone()[0]
                
                kontekst = f"""
Tabela '{prva_tabela}' ima {len(kolone)} kolona i {ukupno} redova.

Kolone: {', '.join(kolone)}

Prvih 5 redova:
"""
                for red in redovi:
                    kontekst += f"{dict(zip(kolone, red))}\n"
                
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model="qwen/qwen3-32b",
                    messages=[
                        {"role": "system", "content": f"""Ti si ekspert za analizu elektro podataka u rudniku.

{kontekst}

Kolone sa `a` na kraju su amperi (struja), sa `r` su radna snaga.
`ts1`, `ts2` su trafo stanice.
`e1` do `e7` su etaže (spratovi).
`m`, `d`, `s`, `h` su mjesec, dan, sat, godina.

Odgovaraj na srpskom (ijekavica). Budi precizan i koristi brojke."""},
                        {"role": "user", "content": pitanje}
                    ],
                    temperature=0.3,
                    max_tokens=2000
                )
                
                odgovor = response.choices[0].message.content
                
                st.success("✅ Analiza završena!")
                st.markdown("### 📊 Rezultat analize")
                st.write(odgovor)
                
                conn.close()
                
        except Exception as e:
            st.error(f"❌ Greška: {str(e)}")

# ========== PREGLED PODATAKA ==========
if uploaded_file:
    st.divider()
    st.subheader("📋 Pregled podataka")
    
    try:
        conn = sqlite3.connect("baza.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabele = [row[0] for row in cursor.fetchall()]
        
        if tabele:
            prva_tabela = tabele[0]
            query = f"SELECT * FROM `{prva_tabela}` LIMIT 100"
            df = pd.read_sql_query(query, conn)
            st.dataframe(df, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Ukupno redova", len(df))
            with col2:
                st.metric("Broj kolona", len(df.columns))
            with col3:
                st.metric("Veličina fajla", f"{uploaded_file.size / 1024:.1f} KB")
        
        conn.close()
    except Exception as e:
        st.error(f"Greška: {str(e)}")

st.divider()
st.caption("💡 Podržani formati: CSV, Excel (.xlsx), SQLite (.db), SQL dump (.sql)")
