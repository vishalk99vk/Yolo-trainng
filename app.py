import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os, zipfile, io, sqlite3, hashlib, random
import pandas as pd
from PIL import Image

# --- STYLING & UI ---
st.set_page_config(layout="wide", page_title="Enterprise YOLO Labeller")

st.markdown("""
    <style>
    rect.bounding-box { stroke-width: 1px !important; }
    .stSidebar { background-color: #111; }
    .main-header { color: #ff4b4b; font-size: 2rem; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE ENGINE ---
conn = sqlite3.connect('yolo_platform.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, skus TEXT, creator TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS assignments (p_id INTEGER, username TEXT)')
conn.commit()

def hash_pw(password): return hashlib.sha256(str.encode(password)).hexdigest()

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.title("🛂 Access Control")
    mode = st.sidebar.radio("Entry Type", ["Login", "Register"])
    user = st.sidebar.text_input("Username")
    pw = st.sidebar.text_input("Password", type='password')
    
    if st.sidebar.button("Enter Platform"):
        hpw = hash_pw(pw)
        if mode == "Register":
            role_choice = st.sidebar.selectbox("Register as", ["user", "admin"])
            try:
                c.execute('INSERT INTO users VALUES (?,?,?)', (user, hpw, role_choice))
                conn.commit()
                st.sidebar.success("Account created! Switch to Login.")
            except: st.sidebar.error("Username already taken.")
        else:
            c.execute('SELECT password, role FROM users WHERE username = ?', (user,))
            res = c.fetchone()
            if res and res[0] == hpw:
                st.session_state.logged_in = True
                st.session_state.username = user
                st.session_state.role = res[1]
                st.rerun() # Critical: Refreshes UI to show panels
            else:
                st.sidebar.error("Invalid credentials.")
    st.stop()

# --- LOGGED IN UI ---
st.sidebar.write(f"Logged in as: **{st.session_state.username}** ({st.session_state.role})")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# Logic to determine which panel to show
if st.session_state.role == "admin":
    panel_choice = st.sidebar.selectbox("Current View", ["Admin Control Panel", "User Labeling Workspace"])
else:
    panel_choice = "User Labeling Workspace"

# ==========================================
# 🛑 ADMIN PANEL
# ==========================================
if panel_choice == "Admin Control Panel":
    st.markdown("<div class='main-header'>🛠️ Admin Management Panel</div>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🚀 Project Creation", "👥 Assignments & Management"])
    
    with tab1:
        p_name = st.text_input("Project Name")
        sku_type = st.radio("SKU Input Method", ["Manual Entry", "Excel/CSV Upload"])
        
        sku_list = []
        if sku_type == "Manual Entry":
            sku_raw = st.text_area("SKUs (Comma separated)")
            sku_list = [x.strip() for x in sku_raw.split(",") if x.strip()]
        else:
            uploaded_sku = st.file_uploader("Upload SKU File", type=['xlsx', 'csv'])
            if uploaded_sku:
                df = pd.read_csv(uploaded_sku) if uploaded_sku.name.endswith('.csv') else pd.read_excel(uploaded_sku)
                sku_list = df.iloc[:, 0].dropna().astype(str).tolist()

        up_images = st.file_uploader("Upload Image Dataset", accept_multiple_files=True)
        
        if st.button("Create Project"):
            if p_name and sku_list and up_images:
                sku_str = ",".join(sku_list)
                c.execute('INSERT INTO projects (name, skus, creator) VALUES (?,?,?)', (p_name, sku_str, st.session_state.username))
                pid = c.lastrowid
                conn.commit()
                
                # Save Images
                path = f"data/proj_{pid}"
                os.makedirs(path, exist_ok=True)
                for f in up_images:
                    with open(os.path.join(path, f.name), "wb") as out:
                        out.write(f.getvalue())
                st.success(f"Project '{p_name}' created. All files uploaded successfully!")
            else: st.error("Please provide project name, SKUs, and images.")

    with tab2:
        st.subheader("Manage User Access")
        c.execute('SELECT id, name FROM projects')
        all_p = c.fetchall()
        c.execute('SELECT username FROM users WHERE role = "user"')
        all_u = [u[0] for u in c.fetchall()]
        
        if all_p and all_u:
            sel_p = st.selectbox("Select Project", all_p, format_func=lambda x: x[1])
            sel_u = st.selectbox("Select User", all_u)
            if st.button("Assign Project to User"):
                c.execute('INSERT INTO assignments VALUES (?,?)', (sel_p[0], sel_u))
                conn.commit()
                st.success(f"Assigned {sel_p[1]} to {sel_u}")
        else: st.info("Create a project and register users to see assignment options.")

# ==========================================
# 🖍️ USER PANEL
# ==========================================
else:
    st.markdown("<div class='main-header'>🖍️ Labeling Workspace</div>", unsafe_allow_html=True)
    
    # Admins see all projects; Users see assigned ones
    if st.session_state.role == "admin":
        c.execute('SELECT id, name, skus FROM projects')
    else:
        c.execute('''SELECT p.id, p.name, p.skus FROM projects p 
                     JOIN assignments a ON p.id = a.p_id WHERE a.username = ?''', (st.session_state.username,))
    
    assigned_projs = c.fetchall()
    
    if not assigned_projs:
        st.warning("No projects assigned to you. Contact the Admin.")
    else:
        project = st.selectbox("Current Project", assigned_projs, format_func=lambda x: x[1])
        pid, pname, pskus = project
        labels = pskus.split(",")
        p_path = f"data/proj_{pid}"
        
        if os.path.exists(p_path):
            img_list = os.listdir(p_path)
            img_name = st.selectbox("Select Image", img_list)
            
            # Workspace Controls
            col1, col2 = st.columns([1, 4])
            with col1:
                rot = st.slider("Rotate Image", 0, 270, 0, 90)
                st.info("💡 Hint: Zoom with Ctrl + Mousewheel")
                
            with col2:
                # Image Processing
                full_path = os.path.join(p_path, img_name)
                with Image.open(full_path) as im:
                    rotated = im.rotate(-rot, expand=True)
                    temp_p = "temp_view.jpg"
                    rotated.save(temp_p)
                
                # Annotation (Thin lines via CSS)
                new_ann = detection(image_path=temp_p, label_list=labels, key=f"lab_{pid}_{img_name}_{rot}")
                
            # Export (ZIP Format)
            if st.button("📦 Build YOLO Dataset ZIP"):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("data.yaml", f"nc: {len(labels)}\nnames: {labels}\ntrain: images/train\nval: images/val")
                    # (Simplified export for production)
                    for n in img_list:
                        z.write(os.path.join(p_path, n), f"images/train/{n}")
                st.download_button("📥 Download My Work", buf.getvalue(), f"{pname}_labels.zip")
