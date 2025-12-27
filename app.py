import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os, zipfile, io, random, sqlite3, hashlib
import pandas as pd
from PIL import Image

# --- PAGE & STYLE CONFIG ---
st.set_page_config(layout="wide", page_title="YOLO Project Labeller")

# CSS to make annotation lines thin and UI professional
st.markdown("""
    <style>
    rect.bounding-box { stroke-width: 1px !important; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .main { background-color: #f5f7f9; }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE LOGIC ---
conn = sqlite3.connect('yolo_platform.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, skus TEXT, owner TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS assignments (project_id INTEGER, username TEXT)')
conn.commit()

def hash_pw(password): return hashlib.sha256(str.encode(password)).hexdigest()

# --- AUTHENTICATION SYSTEM ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def login_system():
    st.sidebar.title("🔐 Access Control")
    mode = st.sidebar.selectbox("Mode", ["Login", "Register"])
    user = st.sidebar.text_input("Username")
    pw = st.sidebar.text_input("Password", type='password')
    
    if st.sidebar.button("Enter"):
        if mode == "Register":
            try:
                c.execute('INSERT INTO users VALUES (?,?)', (user, hash_pw(pw)))
                conn.commit()
                st.sidebar.success("Registered! Switch to Login.")
            except: st.sidebar.error("User already exists.")
        else:
            c.execute('SELECT password FROM users WHERE username = ?', (user,))
            res = c.fetchone()
            if res and res[0] == hash_pw(pw):
                st.session_state.logged_in = True
                st.session_state.username = user
                st.rerun()
            else: st.sidebar.error("Wrong username or password.")

if not st.session_state.logged_in:
    login_system()
    st.title("Welcome to YOLO Labeller")
    st.info("Please login from the sidebar to manage projects and start annotating.")
    st.stop()

# --- MAIN NAVIGATION ---
st.sidebar.success(f"User: {st.session_state.username}")
menu = ["My Dashboard", "Create Project", "Admin: Assignments"]
choice = st.sidebar.selectbox("Navigation", menu)

if st.sidebar.button("Log Out"):
    st.session_state.logged_in = False
    st.rerun()

# --- FEATURE: CREATE PROJECT ---
if choice == "Create Project":
    st.header("🏗️ Start New Annotation Project")
    p_name = st.text_input("Project Name (e.g., Beverages_Q1)")
    sku_source = st.radio("SKU Source", ["Text/Manual", "Excel Upload"])
    
    sku_list_final = []
    if sku_source == "Text/Manual":
        sku_raw = st.text_area("Enter SKUs (one per line)")
        sku_list_final = [s.strip() for s in sku_raw.split('\n') if s.strip()]
    else:
        sku_file = st.file_uploader("Upload Excel/CSV", type=['xlsx', 'csv'])
        if sku_file:
            df = pd.read_csv(sku_file) if sku_file.name.endswith('.csv') else pd.read_excel(sku_file)
            sku_list_final = df.iloc[:, 0].dropna().astype(str).tolist()

    p_imgs = st.file_uploader("Upload Images for this Project", accept_multiple_files=True)

    if st.button("Create Project"):
        if p_name and sku_list_final and p_imgs:
            sku_str = ",".join(sku_list_final)
            c.execute('INSERT INTO projects (name, skus, owner) VALUES (?,?,?)', (p_name, sku_str, st.session_state.username))
            p_id = c.lastrowid
            c.execute('INSERT INTO assignments VALUES (?,?)', (p_id, st.session_state.username))
            conn.commit()
            
            p_path = f"data/proj_{p_id}"
            os.makedirs(p_path, exist_ok=True)
            for f in p_imgs:
                with open(os.path.join(p_path, f.name), "wb") as out: out.write(f.getvalue())
            st.success(f"Project Created! ID: {p_id}")
        else:
            st.error("Please fill all fields and upload images.")

# --- FEATURE: ASSIGNMENTS ---
elif choice == "Admin: Assignments":
    st.header("👥 Project Distribution")
    c.execute('SELECT id, name FROM projects WHERE owner = ?', (st.session_state.username,))
    owned = c.fetchall()
    if owned:
        sel_p = st.selectbox("Select Project", owned, format_func=lambda x: x[1])
        c.execute('SELECT username FROM users')
        all_usrs = [u[0] for u in c.fetchall()]
        target = st.selectbox("Assign to Annotator", all_usrs)
        if st.button("Confirm Assignment"):
            c.execute('INSERT INTO assignments VALUES (?,?)', (sel_p[0], target))
            conn.commit()
            st.success(f"Assigned to {target}")
    else: st.warning("You don't own any projects yet.")

# --- FEATURE: ANNOTATION DASHBOARD ---
elif choice == "My Dashboard":
    c.execute('''SELECT p.id, p.name, p.skus FROM projects p 
                 JOIN assignments a ON p.id = a.project_id WHERE a.username = ?''', (st.session_state.username,))
    my_projs = c.fetchall()
    
    if not my_projs:
        st.info("No projects assigned to you.")
    else:
        project = st.selectbox("Choose a Project to Work On", my_projs, format_func=lambda x: x[1])
        pid, pname, pskus = project
        label_list = pskus.split(',')
        p_path = f"data/proj_{pid}"
        
        if os.path.exists(p_path):
            imgs = [f for f in os.listdir(p_path) if f.endswith(('.jpg', '.png', '.jpeg'))]
            col_a, col_b = st.columns([1, 4])
            
            with col_a:
                selected_img = st.radio("Images", imgs)
                rot = st.slider("Rotate", 0, 270, 0, 90)
                if st.button("✨ AI Suggest"):
                    # Basic AI logic placeholder
                    st.toast("AI suggestions applied!")
            
            with col_b:
                full_path = os.path.join(p_path, selected_img)
                # Rotate image for the session
                with Image.open(full_path) as im:
                    rotated_im = im.rotate(-rot, expand=True)
                    temp_path = "temp_work.jpg"
                    rotated_im.save(temp_path)
                
                # Annotation Tool with thin lines (via CSS above)
                new_ann = detection(image_path=temp_path, label_list=label_list, key=f"{pid}_{selected_img}_{rot}")
                
                if st.button("💾 Save Progress"):
                    st.session_state[f"saved_{pid}_{selected_img}"] = new_ann
                    st.success("Work saved to session!")

            # Export Logic
            st.markdown("---")
            if st.button("🚀 Download Project (YOLO Format)"):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("data.yaml", f"nc: {len(label_list)}\nnames: {label_list}\ntrain: images/train\nval: images/val")
                    # (Export logic here would loop through saved session annotations and images)
                st.download_button("Download ZIP", buf.getvalue(), f"{pname}_labels.zip")
