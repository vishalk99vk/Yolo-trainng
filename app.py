import streamlit as st
import os
import json
import uuid
import zipfile
import hashlib
from io import BytesIO
import pandas as pd
from PIL import Image
from datetime import datetime

# --- SETTINGS ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
ANNOTATIONS_DIR = os.path.join(DATA_DIR, "annotations")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

for d in [DATA_DIR, PROJECTS_DIR, ANNOTATIONS_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

try:
    from streamlit_drawable_canvas import st_canvas
except ImportError:
    st.error("Missing dependency: `pip install streamlit-drawable-canvas`")
    st.stop()

# --- HELPERS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def load_json(file_path, default=None):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f: return json.load(f)
    return default if default is not None else {}

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f, indent=4)

def logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

# --- MAIN NAVIGATION ---
def main():
    st.set_page_config(page_title="YOLO Annotator Pro", layout="wide")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_page()
        else:
            user_page()

def login_page():
    st.header("🔑 YOLO Annotation Tool")
    u_name = st.text_input("Username")
    u_pass = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        users = load_json(USERS_FILE)
        if u_name == 'admin' and u_pass == 'admin':
            st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
            st.rerun()
        elif u_name in users and users[u_name]['password'] == hash_password(u_pass):
            st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
            st.rerun()
        else: st.error("Invalid credentials")

# --- ADMIN PANEL ---
def admin_page():
    st.sidebar.title(f"Admin: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Navigation", ["Projects", "Users"])

    if menu == "Projects":
        st.header("Project Management")
        with st.expander("➕ New Project"):
            p_name = st.text_input("Project Name")
            p_file = st.file_uploader("Upload Product List (CSV)", type=['csv'])
            if st.button("Create") and p_name and p_file:
                df = pd.read_csv(p_file)
                p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
                save_json(os.path.join(PROJECTS_DIR, f"{p_name}.json"), {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}})
                st.rerun()

        available = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
        if available:
            sel_p = st.selectbox("Select Project", available)
            p_path = os.path.join(PROJECTS_DIR, f"{sel_p}.json")
            p = load_json(p_path)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Add Content")
                up = st.file_uploader("Upload Images", accept_multiple_files=True)
                if up and st.button("Upload"):
                    for f in up:
                        id = str(uuid.uuid4())
                        Image.open(f).save(os.path.join(IMAGES_DIR, f"{id}.png"))
                        p['images'].append({'id': id, 'name': f.name})
                    save_json(p_path, p); st.rerun()
            with col2:
                st.subheader("Assignments")
                users = list(load_json(USERS_FILE).keys())
                u_task = st.selectbox("Assign To", users)
                avail = [i['id'] for i in p['images']]
                sel = st.multiselect("Select Images", avail)
                if st.button("Assign"):
                    if u_task not in p['access_users']: p['access_users'].append(u_task)
                    p['assignments'].setdefault(u_task, []).extend(sel)
                    save_json(p_path, p); st.success("Assigned!")

    elif menu == "Users":
        st.header("User Management")
        u_acc = load_json(USERS_FILE)
        un = st.text_input("Username")
        pw = st.text_input("Password")
        if st.button("Create User"):
            u_acc[un] = {'password': hash_password(pw)}; save_json(USERS_FILE, u_acc); st.success("Created!")

# --- USER PANEL (LAYERED FIX) ---
def user_page():
    st.sidebar.title(f"Annotator: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    
    available = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
    my_projs = [pn for pn in available if st.session_state.username in load_json(os.path.join(PROJECTS_DIR, f"{pn}.json")).get('access_users', [])]
    
    if not my_projs:
        st.info("No projects assigned.")
        return

    sel_p = st.selectbox("Project", my_projs)
    p = load_json(os.path.join(PROJECTS_DIR, f"{sel_p}.json"))
    my_imgs = p['assignments'].get(st.session_state.username, [])

    if not my_imgs:
        st.warning("No images assigned.")
        return

    if 'img_idx' not in st.session_state: st.session_state.img_idx = 0
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: 
        if st.button("⬅️ Prev") and st.session_state.img_idx > 0:
            st.session_state.img_idx -= 1; st.rerun()
    with c2: st.write(f"**Image {st.session_state.img_idx + 1} / {len(my_imgs)}**")
    with c3:
        if st.button("Next ➡️") and st.session_state.img_idx < len(my_imgs) - 1:
            st.session_state.img_idx += 1; st.rerun()

    img_id = my_imgs[st.session_state.img_idx]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        img = Image.open(img_path).convert("RGB")
        
        # Consistent Sizing
        canvas_width = 800
        scale = canvas_width / img.width
        canvas_height = int(img.height * scale)

        col_ui, col_work = st.columns([1, 4])
        with col_ui:
            st.subheader("Controls")
            label = st.selectbox("Select Class", p['product_list'])
            if st.button("💾 SAVE BOXES", use_container_width=True, type="primary"):
                st.session_state.save_trigger = True
            st.info("Draw boxes directly on the image to the right.")

        with col_work:
            # LAYERED CSS FIX
            # We create a relative container, put the image at the bottom, and canvas on top
            st.markdown(f"""
                <style>
                .canvas-container {{
                    position: relative;
                    width: {canvas_width}px;
                    height: {canvas_height}px;
                }}
                .background-img {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: {canvas_width}px;
                    height: {canvas_height}px;
                    z-index: 1;
                }}
                .stCanvas {{
                    position: absolute !important;
                    top: 0;
                    left: 0;
                    z-index: 2;
                    background-color: transparent !important;
                }}
                </style>
                """, unsafe_allow_html=True)

            # 1. Place the visible image first
            st.image(img, width=canvas_width)
            
            # 2. Place the transparent canvas exactly on top
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#ff0000",
                background_image=None, # Leave this empty to prevent white screen
                update_streamlit=True,
                height=canvas_height,
                width=canvas_width,
                drawing_mode="rect",
                key=f"layered_canvas_{img_id}",
            )

        if st.session_state.get('save_trigger', False):
            st.session_state.save_trigger = False
            if canvas_result.json_data:
                objs = canvas_result.json_data["objects"]
                yolo_data = []
                for o in objs:
                    if o["type"] == "rect":
                        w, h = abs(o["width"]), abs(o["height"])
                        left = o["left"] if o["width"] > 0 else o["left"] + o["width"]
                        top = o["top"] if o["height"] > 0 else o["top"] + o["height"]
                        xn, yn = (left + w/2)/canvas_width, (top + h/2)/canvas_height
                        wn, hn = w/canvas_width, h/canvas_height
                        yolo_data.append({'class': label, 'bbox': [xn, yn, wn, hn]})
                
                ann_path = os.path.join(ANNOTATIONS_DIR, f"{img_id}_{st.session_state.username}.json")
                save_json(ann_path, {"status": "Completed", "annotations": yolo_data})
                st.success("Saved!"); st.rerun()
    else:
        st.error("Image file not found.")

if __name__ == "__main__":
    main()
