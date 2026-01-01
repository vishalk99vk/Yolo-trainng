import streamlit as st
import os
import json
import uuid
import zipfile
import hashlib
import base64
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# --- SETUP PATHS ---
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
    st.error("Run: pip install streamlit-drawable-canvas")
    st.stop()

# --- HELPERS ---
def get_image_base64(img):
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

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
        if st.session_state.user_type == 'admin': admin_page()
        else: user_page()

def login_page():
    st.header("🔑 YOLO Annotation Tool")
    col1, _ = st.columns([1, 1])
    with col1:
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True, type="primary"):
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
            
            if st.button("📦 Download YOLO ZIP", type="primary"):
                download_yolo(sel_p, p)

    elif menu == "Users":
        st.header("User Management")
        u_acc = load_json(USERS_FILE)
        un = st.text_input("Username")
        pw = st.text_input("Password")
        if st.button("Create User"):
            u_acc[un] = {'password': hash_password(pw)}; save_json(USERS_FILE, u_acc); st.success("Created!")

# --- USER PANEL (THE ULTIMATE FIX) ---
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
    
    # Navigation
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
        
        # Determine Display Size
        canvas_width = 800
        scale = canvas_width / img.width
        canvas_height = int(img.height * scale)
        resized = img.resize((canvas_width, canvas_height), Image.LANCZOS)
        
        # Convert to B64 for the Canvas
        b64_str = get_image_base64(resized)

        col_left, col_right = st.columns([1, 3])
        with col_left:
            st.subheader("Controls")
            label = st.selectbox("Class", p['product_list'])
            if st.button("💾 SAVE", use_container_width=True, type="primary"):
                st.session_state.save_trigger = True
            st.divider()
            st.write("Preview:")
            st.image(resized)

        with col_right:
            # FORCE RE-RENDER CSS
            st.markdown(f"""
                <style>
                iframe[title="streamlit_drawable_canvas.st_canvas"] {{
                    background-image: url("{b64_str}") !important;
                    background-size: cover !important;
                }}
                </style>
                """, unsafe_allow_html=True)
            
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#ff0000",
                background_image=resized, # Still pass the PIL object as fallback
                update_streamlit=True,
                height=canvas_height,
                width=canvas_width,
                drawing_mode="rect",
                key=f"canvas_ultimate_{img_id}", # Unique key per image
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
                        # Normalized YOLO coords
                        xn, yn = (left + w/2)/canvas_width, (top + h/2)/canvas_height
                        wn, hn = w/canvas_width, h/canvas_height
                        yolo_data.append({'class': label, 'bbox': [xn, yn, wn, hn]})
                
                ann_path = os.path.join(ANNOTATIONS_DIR, f"{img_id}_{st.session_state.username}.json")
                save_json(ann_path, {"status": "Completed", "annotations": yolo_data})
                st.success("Saved!"); st.rerun()

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            img_id = im['id']
            for u in p['access_users']:
                ap = os.path.join(ANNOTATIONS_DIR, f"{img_id}_{u}.json")
                if os.path.exists(ap):
                    data = load_json(ap)
                    if data.get('status') == "Completed":
                        z.write(os.path.join(IMAGES_DIR, f"{img_id}.png"), f"images/{img_id}.png")
                        txt = ""
                        for a in data['annotations']:
                            idx = p['product_list'].index(a['class'])
                            txt += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                        z.writestr(f"labels/{img_id}.txt", txt)
        z.writestr("data.yaml", f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images")
    st.download_button("Download", buf.getvalue(), f"{name}.zip")

if __name__ == "__main__":
    main()
