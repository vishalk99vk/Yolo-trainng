import streamlit as st
import os
import cv2
import numpy as np
import json
import uuid
import zipfile
import hashlib
from PIL import Image
from streamlit_image_annotation import detection
from datetime import datetime

# --- 1. DIRECTORY & CONFIG SETUP ---
BASE_DIR = os.path.abspath("retail_data")
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
ANNOTATIONS_DIR = os.path.join(BASE_DIR, "annotations")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
USERS_FILE = os.path.join(BASE_DIR, "users.json")

for d in [BASE_DIR, PROJECTS_DIR, ANNOTATIONS_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- 2. HELPERS ---
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

# --- 3. MAIN APP ---
def main():
    st.set_page_config(page_title="SKU Annotator Pro", layout="wide")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_page()
        else:
            user_panel()

def login_page():
    st.title("🔑 Retail SKU Annotator")
    col1, _ = st.columns([1, 1])
    with col1:
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            users = load_json(USERS_FILE)
            if u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            elif u_name in users and users[u_name]['password'] == hash_password(u_pass):
                st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
                st.rerun()
            else:
                st.error("Invalid credentials")

# --- 4. ADMIN PANEL ---
def admin_page():
    st.sidebar.title(f"Admin: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Navigation", ["Manage Projects", "User Management"])

    if menu == "Manage Projects":
        st.header("Project Management")
        
        # Create Project
        with st.expander("🏗️ Create New Project"):
            p_name = st.text_input("Project Name")
            p_list_input = st.text_area("Product List (comma separated)", "product, SKU_A, SKU_B")
            if st.button("Create Project"):
                labels = [x.strip() for x in p_list_input.split(",")]
                save_json(os.path.join(PROJECTS_DIR, f"{p_name}.json"), {
                    'labels': labels, 'images': [], 'assignments': {}
                })
                st.success("Project Created!")

        # Project Operations
        available = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
        if available:
            sel_p = st.selectbox("Select Project", available)
            p_path = os.path.join(PROJECTS_DIR, f"{sel_p}.json")
            proj = load_json(p_path)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Upload Images")
                up = st.file_uploader("Select SKU Photos", accept_multiple_files=True)
                if up and st.button("Store Images"):
                    for f in up:
                        img_id = str(uuid.uuid4())[:8] + "_" + f.name
                        with open(os.path.join(IMAGES_DIR, img_id), "wb") as file:
                            file.write(f.getbuffer())
                        proj['images'].append(img_id)
                    save_json(p_path, proj)
                    st.rerun()

            with col2:
                st.subheader("Assign Tasks")
                users = list(load_json(USERS_FILE).keys())
                target_u = st.selectbox("Target User", users)
                if st.button("Assign All Images"):
                    proj['assignments'][target_u] = proj['images']
                    save_json(p_path, proj)
                    st.success(f"Assigned to {target_u}")

            st.divider()
            if st.button("📦 Generate & Download YOLO Dataset", type="primary"):
                download_yolo(sel_p, proj)

    elif menu == "User Management":
        st.header("User Management")
        u_acc = load_json(USERS_FILE)
        un = st.text_input("New Username")
        pw = st.text_input("New Password")
        if st.button("Create Account"):
            u_acc[un] = {'password': hash_password(pw)}
            save_json(USERS_FILE, u_acc)
            st.success("User added!")

# --- 5. USER PANEL (USING YOUR WORKING LOGIC) ---
def user_panel():
    st.sidebar.title(f"👤 {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    
    projects = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
    my_projs = [p for p in projects if st.session_state.username in load_json(os.path.join(PROJECTS_DIR, f"{p}.json")).get('assignments', {})]
    
    if not my_projs:
        st.info("No projects assigned to you yet.")
        return

    sel_p = st.selectbox("Current Project", my_projs)
    proj = load_json(os.path.join(PROJECTS_DIR, f"{sel_p}.json"))
    my_imgs = proj['assignments'].get(st.session_state.username, [])

    if 'idx' not in st.session_state: st.session_state.idx = 0
    
    # Nav controls
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: 
        if st.button("⬅️ Prev") and st.session_state.idx > 0: st.session_state.idx -= 1; st.rerun()
    with c2: st.write(f"Image {st.session_state.idx + 1} / {len(my_imgs)}")
    with c3:
        if st.button("Next ➡️") and st.session_state.idx < len(my_imgs)-1: st.session_state.idx += 1; st.rerun()

    img_name = my_imgs[st.session_state.idx]
    img_path = os.path.join(IMAGES_DIR, img_name)
    
    # LOAD IMAGE FOR METADATA
    img_cv = cv2.imread(img_path)
    h, w, _ = img_cv.shape

    # ANNOTATION TOOL (Your working logic)
    # Note: We use the filename as the key to ensure state refresh
    new_annotations = detection(
        image_path=img_path,
        label_list=proj['labels'],
        bboxes=[], labels=[],
        key=f"ann_{img_name}"
    )

    if st.button("Submit Annotations", type="primary"):
        if new_annotations:
            # Save in JSON format for the tool
            ann_file = os.path.join(ANNOTATIONS_DIR, f"{img_name}_{st.session_state.username}.json")
            save_json(ann_file, new_annotations)
            
            # Also save in YOLO TXT format for your RF-DETR
            txt_name = os.path.splitext(img_name)[0] + ".txt"
            with open(os.path.join(BASE_DIR, "labels", txt_name), "w") as f:
                for ann in new_annotations:
                    bx = ann['bbox'] # [x, y, width, height]
                    label_idx = proj['labels'].index(ann['label'])
                    xc, yc = (bx[0] + bx[2]/2) / w, (bx[1] + bx[3]/2) / h
                    nw, nh = bx[2] / w, bx[3] / h
                    f.write(f"{label_idx} {xc} {yc} {nw} {nh}\n")
            
            st.success(f"Saved {len(new_annotations)} products!")

# --- 6. DATASET EXPORT ---
def download_yolo(name, proj):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for img_name in proj['images']:
            # Find any completed annotations for this image
            # In this simple version, we look for the first one found
            found = False
            for f in os.listdir(ANNOTATIONS_DIR):
                if f.startswith(img_name):
                    data = load_json(os.path.join(ANNOTATIONS_DIR, f))
                    img_path = os.path.join(IMAGES_DIR, img_name)
                    img_cv = cv2.imread(img_path)
                    h, w, _ = img_cv.shape
                    
                    z.write(img_path, f"images/{img_name}")
                    txt_content = ""
                    for ann in data:
                        bx = ann['bbox']
                        l_idx = proj['labels'].index(ann['label'])
                        xc, yc = (bx[0] + bx[2]/2) / w, (bx[1] + bx[3]/2) / h
                        nw, nh = bx[2] / w, bx[3] / h
                        txt_content += f"{l_idx} {xc} {yc} {nw} {nh}\n"
                    
                    z.writestr(f"labels/{os.path.splitext(img_name)[0]}.txt", txt_content)
                    found = True
                    break
        
        yaml = f"names: {proj['labels']}\nnc: {len(proj['labels'])}\ntrain: images\nval: images"
        z.writestr("data.yaml", yaml)
        
    st.download_button("📩 Download Dataset", buf.getvalue(), f"{name}_dataset.zip")

from io import BytesIO
if __name__ == "__main__":
    main()
