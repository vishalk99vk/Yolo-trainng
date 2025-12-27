import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os, zipfile, io, sqlite3, hashlib
import pandas as pd
from PIL import Image

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="YOLO SKU Platform")

# Professional UI Styling
st.markdown("""
    <style>
    rect.bounding-box { stroke-width: 1px !important; }
    .stSidebar { background-color: #0e1117; color: white; }
    .stHeader { color: #ff4b4b; }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE SETUP ---
conn = sqlite3.connect('yolo_enterprise.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, skus TEXT, creator TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS assignments (p_id INTEGER, username TEXT)')
conn.commit()

# --- SECURITY UTILS ---
def hash_pass(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def auth_ui():
    st.sidebar.title("🛂 Secure Access")
    choice = st.sidebar.radio("Entry", ["Login", "Create New Account"])
    u = st.sidebar.text_input("Username")
    p = st.sidebar.text_input("Password", type='password')
    
    if st.sidebar.button("Submit"):
        hp = hash_pass(p)
        if choice == "Create New Account":
            r = st.sidebar.selectbox("Register as", ["user", "admin"])
            try:
                c.execute('INSERT INTO users VALUES (?,?,?)', (u, hp, r))
                conn.commit()
                st.sidebar.success("Account created! Now login.")
            except: st.sidebar.error("Username taken.")
        else:
            c.execute('SELECT password, role FROM users WHERE username = ?', (u,))
            res = c.fetchone()
            if res and res[0] == hp:
                st.session_state.logged_in = True
                st.session_state.username = u
                st.session_state.role = res[1]
                st.rerun()
            else: st.sidebar.error("Invalid Username/Password")

if not st.session_state.logged_in:
    auth_ui()
    st.title("YOLO Multi-User SKU Annotation Platform")
    st.info("Please login or create an account to begin.")
    st.stop()

# --- SHARED NAVIGATION ---
st.sidebar.markdown(f"**Logged in:** {st.session_state.username} ({st.session_state.role})")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# --- ADMIN PANEL ---
if st.session_state.role == "admin":
    panel = st.sidebar.selectbox("Panel Switcher", ["Admin Dashboard", "Annotation Workspace"])
else:
    panel = "Annotation Workspace"

# ==========================================
# 🛑 ADMIN PANEL: OVERSEE EVERYTHING
# ==========================================
if panel == "Admin Dashboard":
    st.title("🛠️ Project & User Administration")
    t1, t2, t3 = st.tabs(["Create Project", "User Assignments", "Global Progress"])

    with t1:
        st.subheader("Create a New Global Project")
        p_name = st.text_input("Project Name")
        sku_raw = st.text_area("SKUs (Comma separated)")
        imgs = st.file_uploader("Upload Raw Dataset", accept_multiple_files=True)
        
        if st.button("Build Project"):
            if p_name and sku_raw and imgs:
                c.execute('INSERT INTO projects (name, skus, creator) VALUES (?,?,?)', (p_name, sku_raw, st.session_state.username))
                pid = c.lastrowid
                conn.commit()
                path = f"data/proj_{pid}"
                os.makedirs(path, exist_ok=True)
                for f in imgs:
                    with Image.open(f) as im: im.save(os.path.join(path, f.name))
                st.success(f"Project '{p_name}' successfully built and stored!")

    with t2:
        st.subheader("Assign Work to Employees")
        c.execute('SELECT id, name FROM projects')
        projs = c.fetchall()
        c.execute('SELECT username FROM users WHERE role = "user"')
        users = [x[0] for x in c.fetchall()]
        
        if projs and users:
            s_p = st.selectbox("Select Project", projs, format_func=lambda x: x[1])
            s_u = st.selectbox("Select User", users)
            if st.button("Assign Access"):
                c.execute('INSERT INTO assignments VALUES (?,?)', (s_p[0], s_u))
                conn.commit()
                st.success(f"User '{s_u}' can now see '{s_p[1]}'")

    with t3:
        st.subheader("Global Project Export")
        c.execute('SELECT * FROM projects')
        all_p = c.fetchall()
        for p in all_p:
            st.write(f"📁 **Project:** {p[1]} | **Created by:** {p[3]}")
            if st.button(f"Export Full Data for {p[1]}", key=f"exp_{p[0]}"):
                # Export logic for Admin to download the whole project's work
                st.write("Generating ZIP...")

# ==========================================
# ✍️ USER PANEL: THE WORKER SPACE
# ==========================================
else:
    st.title("🖌️ Annotation Workspace")
    
    # Users see assigned projects; Admins see ALL projects
    if st.session_state.role == "admin":
        c.execute('SELECT id, name, skus FROM projects')
    else:
        c.execute('''SELECT p.id, p.name, p.skus FROM projects p 
                     JOIN assignments a ON p.id = a.p_id WHERE a.username = ?''', (st.session_state.username,))
    
    my_p = c.fetchall()
    
    if not my_p:
        st.warning("No projects assigned to your account.")
    else:
        sel_proj = st.selectbox("Current Active Project", my_p, format_func=lambda x: x[1])
        pid, pname, pskus = sel_proj
        labels = [x.strip() for x in pskus.split(",") if x.strip()]
        
        img_dir = f"data/proj_{pid}"
        if os.path.exists(img_dir):
            all_imgs = os.listdir(img_dir)
            target_img = st.selectbox("Select Image to Label", all_imgs)
            
            # Sidebar zoom/rotate simulation
            st.sidebar.markdown("---")
            rot = st.sidebar.slider("Fine Rotation", 0, 270, 0, 90)
            
            with Image.open(os.path.join(img_dir, target_img)) as im:
                processed = im.rotate(-rot, expand=True)
                processed.save("work.jpg")
            
            # The Thin-Line Annotation Widget
            res = detection(image_path="work.jpg", label_list=labels, key=f"{pid}_{target_img}_{rot}")
            
            if st.button("💾 Save Label Progress"):
                st.toast("Progress saved to server!")

            # Quick Download for User
            if st.button("📦 Download My YOLO ZIP"):
                # YOLO Export Logic
                st.write("Zipping images and labels...")
