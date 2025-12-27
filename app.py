import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# 1. Safe Import
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS_LIB = True
except ImportError:
    HAS_CANVAS_LIB = False

# Constants
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# Data Persistence
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f: return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f)

def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r') as f: return json.load(f)
    return {}

def save_projects(projects):
    with open(PROJECTS_FILE, 'w') as f: json.dump(projects, f)

# Session State Init
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_type' not in st.session_state: st.session_state.user_type = None
if 'username' not in st.session_state: st.session_state.username = None
if 'use_canvas' not in st.session_state: st.session_state.use_canvas = HAS_CANVAS_LIB

def logout():
    st.session_state.logged_in = False
    st.rerun()

def main():
    st.title("YOLO Annotation Tool")
    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_page()
        else:
            user_page()

def login_page():
    st.header("Login")
    u_type = st.selectbox("Type", ["user", "admin"])
    u_name = st.text_input("Username")
    u_pass = st.text_input("Password", type="password")
    if st.button("Login"):
        users = load_users()
        if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
            st.session_state.logged_in, st.session_state.user_type, st.session_state.username = True, 'admin', 'admin'
            st.rerun()
        elif u_type == 'user' and u_name in users and users[u_name]['password'] == u_pass:
            st.session_state.logged_in, st.session_state.user_type, st.session_state.username = True, 'user', u_name
            st.rerun()
        else:
            st.error("Invalid credentials")

# --- ADMIN SECTION ---
def admin_page():
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.selectbox("Menu", ["Projects", "Users", "Review & Progress"])
    
    if menu == "Projects":
        manage_projects_ui()
    elif menu == "Users":
        add_user_ui()
    elif menu == "Review & Progress":
        review_ui()

def manage_projects_ui():
    st.subheader("Manage Projects")
    projs = load_projects()
    
    with st.expander("Create New Project"):
        p_name = st.text_input("Project Name")
        p_list = st.text_area("Classes (comma separated)")
        if st.button("Create"):
            projs[p_name] = {'product_list': [x.strip() for x in p_list.split(',') if x.strip()],
                             'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
            save_projects(projs)
            st.rerun()

    if projs:
        sel_p = st.selectbox("Select Project", list(projs.keys()))
        p = projs[sel_p]
        
        # Upload
        up = st.file_uploader("Upload Images", accept_multiple_files=True)
        if up and st.button("Save Images"):
            for f in up:
                id = str(uuid.uuid4())
                with open(os.path.join(IMAGES_DIR, f"{id}.png"), "wb") as img_f: img_f.write(f.getvalue())
                p['images'].append({'id': id, 'date': datetime.now().strftime("%Y-%m-%d")})
            save_projects(projs)
            st.rerun()

        # Assignments
        users = list(load_users().keys())
        u = st.selectbox("Assign to User", users)
        if st.button("Grant Project Access"):
            if u not in p['access_users']: p['access_users'].append(u)
            save_projects(projs)
        
        assigned_to_him = p['assignments'].get(u, [])
        avail = [i['id'] for i in p['images'] if i['id'] not in assigned_to_him]
        to_assign = st.multiselect("Assign Images", avail)
        if st.button("Confirm Assign"):
            p['assignments'].setdefault(u, []).extend(to_assign)
            save_projects(projs)
            st.rerun()

        st.divider()
        if st.button("Download YOLO Dataset"):
            download_yolo(sel_p, p)

def add_user_ui():
    users = load_users()
    st.subheader("User Management")
    new_u = st.text_input("Username")
    new_p = st.text_input("Password")
    if st.button("Add User"):
        users[new_u] = {'password': new_p}
        save_users(users)
        st.success("Added")
    st.write("Current Users:", list(users.keys()))

def review_ui():
    st.subheader("Progress Review")
    projs = load_projects()
    sel_p = st.selectbox("Project", list(projs.keys()))
    p = projs[sel_p]
    
    # Progress Stats
    for u in p['access_users']:
        assigned = p['assignments'].get(u, [])
        done = sum(1 for img in assigned if p.get('statuses', {}).get(img, {}).get(u) == "Completed")
        flagged = sum(1 for img in assigned if p.get('statuses', {}).get(img, {}).get(u) == "Flagged")
        st.write(f"**{u}:** {done}/{len(assigned)} Completed | {flagged} Flagged")

    st.divider()
    sel_u = st.selectbox("Select User to Review Work", p['access_users'])
    assigned = p['assignments'].get(sel_u, [])
    
    for img_id in assigned:
        status = p.get('statuses', {}).get(img_id, {}).get(sel_u, "Pending")
        color = "green" if status == "Completed" else "orange" if status == "Flagged" else "gray"
        
        with st.expander(f"Image: {img_id} | Status: {status}"):
            if img_id in p['annotations'] and sel_u in p['annotations'][img_id]:
                img = Image.open(os.path.join(IMAGES_DIR, f"{img_id}.png")).convert("RGB")
                draw = ImageDraw.Draw(img)
                for ann in p['annotations'][img_id][sel_u]:
                    xc, yc, w, h = ann['bbox']
                    left, top = (xc - w/2) * img.width, (yc - h/2) * img.height
                    right, bottom = (xc + w/2) * img.width, (yc + h/2) * img.height
                    draw.rectangle([left, top, right, bottom], outline="red", width=3)
                st.image(img)
            else:
                st.info("No annotations saved yet.")

# --- USER SECTION ---
def user_page():
    st.sidebar.button("Logout", on_click=logout)
    projs = load_projects()
    access = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not access: return st.warning("No projects assigned.")
    
    p_name = st.selectbox("Project", access)
    p = projs[p_name]
    assigned = p['assignments'].get(st.session_state.username, [])
    
    # Simple status filters
    view_filter = st.radio("View:", ["All", "Pending", "Completed/Flagged"], horizontal=True)

    for img_id in assigned:
        current_status = p.setdefault('statuses', {}).setdefault(img_id, {}).get(st.session_state.username, "Pending")
        
        if view_filter == "Pending" and current_status != "Pending": continue
        if view_filter == "Completed/Flagged" and current_status == "Pending": continue

        path = os.path.join(IMAGES_DIR, f"{img_id}.png")
        if os.path.exists(path):
            img = Image.open(path)
            st.write(f"---")
            st.subheader(f"Image {img_id}")
            st.write(f"Current Status: **{current_status}**")
            
            if st.session_state.use_canvas:
                try:
                    cls = st.selectbox(f"Select Class", p['product_list'], key=f"c_{img_id}")
                    canvas = st_canvas(fill_color="rgba(255,165,0,0.3)", background_image=img,
                                       height=img.height, width=img.width, drawing_mode="rect", key=f"v_{img_id}")
                    
                    col1, col2, col3 = st.columns(3)
                    if col1.button(f"Save & Mark Complete", key=f"s_{img_id}"):
                        if canvas.json_data:
                            objs = canvas.json_data["objects"]
                            anns = [{'class': cls, 'bbox': [o["left"]/img.width + (o["width"]/img.width)/2, 
                                                            o["top"]/img.height + (o["height"]/img.height)/2, 
                                                            o["width"]/img.width, o["height"]/img.height]} 
                                    for o in objs if o["type"] == "rect"]
                            p['annotations'].setdefault(img_id, {})[st.session_state.username] = anns
                            p['statuses'][img_id][st.session_state.username] = "Completed"
                            save_projects(projs)
                            st.rerun()
                    
                    if col2.button(f"Flag (Unclear)", key=f"f_{img_id}"):
                        p['statuses'][img_id][st.session_state.username] = "Flagged"
                        save_projects(projs)
                        st.rerun()
                except:
                    st.session_state.use_canvas = False
                    st.rerun()

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            id = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{id}.png")
            if os.path.exists(img_p): z.write(img_p, f"images/{id}.png")
            if id in p['annotations']:
                txt = ""
                for u, user_anns in p['annotations'][id].items():
                    # Only export if marked as completed
                    if p.get('statuses', {}).get(id, {}).get(u) == "Completed":
                        for a in user_anns:
                            txt += f"{p['product_list'].index(a['class'])} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                if txt: z.writestr(f"labels/{id}.txt", txt)
    st.download_button("Download ZIP", buf.getvalue(), f"{name}.zip")

if __name__ == "__main__":
    main()
