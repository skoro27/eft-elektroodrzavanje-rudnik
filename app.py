import streamlit as st
import sqlite3
import pandas as pd
import re
from groq import Groq
import os
from io import BytesIO

st.set_page_config(page_title="Elektro Održavanje - Rudnik", layout="wide")
st.title("⚡ Elektro Održavanje - Rudnik")
st.caption("Analiza potrošnje energije pomoću Groq AI")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

DB_PATH = "baza.db"


def ocisti_mysql_create(create_sql):
    create_sql = re.sub(r'`', '"', create_sql)
    create_sql = re.sub(r'\bbigint\(\d+\)', 'INTEGER', create_sql, flags=re.I)
    create_sql = re.sub(r'\bint\(\d+\)', 'INTEGER', create_sql, flags=re.I)
    create_sql = re.sub(r'\btinyint\(\d+\)', 'INTEGER', create_sql, flags=re.I)
    create_sql = re.sub(r'\bvarchar\(\d+\)', 'TEXT', create_sql, flags=re.I)
    create_sql = re.sub(r'\bdatetime\b', 'TEXT', create_sql, flags=re.I)
    create_sql = re.sub(r'\bfloat\b', 'REAL', create_sql, flags=re.I)
    create_sql = re.sub(r'\bdouble\b', 'REAL', create_sql, flags=re.I)
    create_sql = re.sub(r'\bdecimal\(\d+,\d+\)', 'REAL', create_sql, flags=re.I)
    create_sql = re.sub(r'COMMENT\s+\'[^\']*\'', '', create_sql, flags=re.I)
    create_sql = re.sub(r'AUTO_INCREMENT', '', create_sql, flags=re.I)
    create_sql = re.sub(r'ENGINE=.*?;', ';', create_sql, flags=re.I | re.S)
    return create_sql


with st.sidebar:
    st.header("📊 Podaci")

    uploaded_file = st.file_uploader(
        "Upload podataka (CSV, Excel, .db, .sql)",
        type=["csv", "xlsx", "xls", "db", "sql", "sqlite", "sqlite3"]
    )

    if uploaded_file:
        file_content = uploaded_file.read()
        file_buffer = BytesIO(file_content)

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            filename = uploaded_file.name.lower()

            if filename.endswith(".csv"):
                try:
                    df = pd.read_csv(file_buffer)
                except pd.errors.EmptyDataError:
                    st.error("❌ CSV fajl je prazan ili nema kolone.")
                    st.stop()

                df.to_sql("podaci", conn, if_exists="replace", index=False)
                st.success(f"✅ CSV učitan! ({len(df)} redova, {len(df.columns)} kolona)")

            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_buffer)
                df.to_sql("podaci", conn, if_exists="replace", index=False)
                st.success(f"✅ Excel učitan! ({len(df)} redova, {len(df.columns)} kolona)")

            elif filename.endswith(".sql"):
                sql_text = file_content.decode("utf-8", errors="ignore")

                create_matches = re.findall(
                    r"CREATE TABLE.*?;",
                    sql_text,
                    flags=re.IGNORECASE | re.DOTALL
                )

                if not create_matches:
                    st.error("❌ Nije pronađena CREATE TABLE naredba u SQL fajlu.")
                    st.stop()

                for create_sql in create_matches:
                    create_sql = ocisti_mysql_create(create_sql)

                    try:
                        cursor.execute(create_sql)
                    except Exception as e:
                        st.warning(f"⚠️ Problem pri kreiranju tabele: {str(e)[:200]}")
                        st.code(create_sql[:800], language="sql")

                insert_matches = re.findall(
                    r"INSERT INTO.*?;",
                    sql_text,
                    flags=re.IGNORECASE | re.DOTALL
                )

                inserted = 0

                for insert_sql in insert_matches:
                    insert_sql = re.sub(r"`", '"', insert_sql)

                    try:
                        cursor.execute(insert_sql)
                        inserted += 1
                    except Exception:
                        pass

                conn.commit()

                if inserted:
                    st.success(f"✅ SQL fajl učitan! INSERT naredbi: {inserted}")
                else:
                    st.warning("⚠️ Tabele su kreirane, ali podaci možda nijesu ubačeni.")

            else:
                with open(DB_PATH, "wb") as f:
                    f.write(file_content)

                st.success("✅ SQLite baza učitana!")

            conn.close()

        except Exception as e:
            st.error(f"❌ Greška pri učitavanju: {str(e)}")

    st.divider()

    if GROQ_API_KEY:
        st.success("🔑 API ključ podešen")
    else:
        st.error("⚠️ API ključ nije podešen!")


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
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tabele = [row[0] for row in cursor.fetchall()]

                if not tabele:
                    st.error("❌ Nema tabela u bazi!")
                    st.stop()

                prva_tabela = tabele[0]

                cursor.execute(f'SELECT * FROM "{prva_tabela}" LIMIT 5')
                kolone = [desc[0] for desc in cursor.description]
                redovi = cursor.fetchall()

                ukupno = cursor.execute(
                    f'SELECT COUNT(*) FROM "{prva_tabela}"'
                ).fetchone()[0]

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
                        {
                            "role": "system",
                            "content": f"""
Ti si ekspert za analizu elektro podataka u rudniku.

{kontekst}

Kolone sa `a` na kraju su amperi, odnosno struja.
Kolone sa `r` su radna snaga.
`ts1`, `ts2` su trafo stanice.
`e1` do `e7` su etaže.
`m`, `d`, `s`, `h` su mjesec, dan, sat, godina.

Odgovaraj na srpskom, ijekavica. Budi precizan i koristi brojke.
"""
                        },
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


if uploaded_file:
    st.divider()
    st.subheader("📋 Pregled podataka")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabele = [row[0] for row in cursor.fetchall()]

        if tabele:
            tabela = st.selectbox("Izaberite tabelu:", tabele)

            query = f'SELECT * FROM "{tabela}" LIMIT 100'
            df = pd.read_sql_query(query, conn)

            st.dataframe(df, use_container_width=True)

            ukupno_redova = pd.read_sql_query(
                f'SELECT COUNT(*) AS broj FROM "{tabela}"',
                conn
            )["broj"][0]

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Ukupno redova", ukupno_redova)

            with col2:
                st.metric("Broj kolona", len(df.columns))

            with col3:
                st.metric("Veličina fajla", f"{uploaded_file.size / 1024:.1f} KB")

        conn.close()

    except Exception as e:
        st.error(f"Greška pri prikazu podataka: {str(e)}")


st.divider()
st.caption("💡 Podržani formati: CSV, Excel (.xlsx), SQLite (.db), SQL dump (.sql)")
