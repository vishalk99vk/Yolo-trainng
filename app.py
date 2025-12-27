import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# 1. Safe Import for Canvas
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
        
        # EXCEL/CSV UPLOAD FOR PRODUCTS
        st.write("Add Product Classes:")
        upload_option = st.radio("Method", ["Manual Entry", "Upload Excel/CSV"], key="prod_method")
        p_list = []
        
        if upload_option == "Manual Entry":
            p_text = st.text_area("Classes (comma separated)")
            p_list = [x.strip() for x in p_text.split(',') if x.strip()]
        else:
            prod_file = st.file_uploader("Upload Product List", type=['xlsx', 'xls', 'csv'])
            if prod_file:
                df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
                p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
                st.info(f"Loaded {len(p_list)} products.")

        if st.button("Create Project"):
            if p_name and p_list:
                projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 
                                 'assignments': {}, 'annotations': {}, 'statuses': {}, 'comments': {}}
                save_projects(projs)
                st.success(f"Project '{p_name}' created!")
                st.rerun()

    if projs:
        st.divider()
        sel_p = st.selectbox("Select Project to Manage", list(projs.keys()))
        p = projs[sel_p]
        
        # Upload Images
        up = st.file_uploader("Upload Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
        if up and st.button("Save Uploaded Images"):
            for f in up:
                id = str(uuid.uuid4())
                with open(os.path.join(IMAGES_DIR, f"{id}.png"), "wb") as img_f: img_f.write(f.getvalue())
                p['images'].append({'id': id, 'date': datetime.now().strftime("%Y-%m-%d")})
            save_projects(projs)
            st.success("Images Saved!")
            st.rerun()

        # Assignments
        all_sys_users = list(load_users().keys())
        u = st.selectbox("Assign Project Access to User", all_sys_users)
        if st.button("Grant Access"):
            if u not in p['access_users']: p['access_users'].append(u)
            save_projects(projs)
            st.success(f"Access granted to {u}")
        
        if p['access_users']:
            target_u = st.selectbox("Assign Specific Images to", p['access_users'], key="target_u")
            assigned_already = p['assignments'].get(target_u, [])
            avail_imgs = [i['id'] for i in p['images'] if i['id'] not in assigned_already]
            to_assign = st.multiselect("Select Images for this User", avail_imgs)
            if st.button("Confirm Assignments"):
                p['assignments'].setdefault(target_u, []).extend(to_assign)
                save_projects(projs)
                st.success("Assigned!")
                st.rerun()

        st.divider()
        if st.button("Download Final YOLO Dataset"):
            download_yolo(sel_p, p)

def add_user_ui():
    users = load_users()
    st.subheader("User Management")
    new_u = st.text_input("New Username")
    new_p = st.text_input("New Password")
    if st.button("Add User Account"):
        if new_u:
            users[new_u] = {'password': new_p}
            save_users(users)
            st.success(f"Account for {new_u} created.")
    st.write("Existing Users:", list(users.keys()))

def review_ui():
    st.subheader("Annotation Review & Comments")
    projs = load_projects()
    if not projs: return st.info("No projects yet.")
    
    sel_p = st.selectbox("Select Project", list(projs.keys()))
    p = projs[sel_p]
    
    sel_u = st.selectbox("Select User to Review", p['access_users'])
    assigned = p['assignments'].get(sel_u, [])
    
    for img_id in assigned:
        status = p.get('statuses', {}).get(img_id, {}).get(sel_u, "Pending")
        comment = p.get('comments', {}).get(img_id, {}).get(sel_u, "")
        
        with st.expander(f"Image: {img_id} | Status: {status}"):
            if comment: st.warning(f"**User Comment:** {comment}")
            
            if img_id in p['annotations'] and sel_u in p['annotations'][img_id]:
                img = Image.open(os.path.join(IMAGES_DIR, f"{img_id}.png")).convert("RGB")
                draw = ImageDraw.Draw(img)
                for ann in p['annotations'][img_id][sel_u]:
                    xc, yc, w, h = ann['bbox']
                    left, top = (xc - w/2) * img.width, (yc - h/2) * img.height
                    right, bottom = (xc + w/2) * img.width, (yc + h/2) * img.height
                    draw.rectangle([left, top, right, bottom], outline="red", width=3)
                    draw.text((left, top), ann['class'], fill="red")
                st.image(img)
            else:
                st.info("No annotations saved for this image.")

# --- USER SECTION ---
def user_page():
    st.sidebar.button("Logout", on_click=logout)
    projs = load_projects()
    access = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not access: return st.warning("You don't have access to any projects.")
    
    p_name = st.selectbox("Current Project", access)
    p = projs[p_name]
    assigned = p['assignments'].get(st.session_state.username, [])
    
    view_filter = st.radio("Show:", ["All", "Pending", "Finished"], horizontal=True)

    for img_id in assigned:
        status = p.setdefault('statuses', {}).setdefault(img_id, {}).get(st.session_state.username, "Pending")
        
        if view_filter == "Pending" and status != "Pending": continue
        if view_filter == "Finished" and status == "Pending": continue

        path = os.path.join(IMAGES_DIR, f"{img_id}.png")
        if os.path.exists(path):
            img = Image.open(path)
            st.divider()
            st.subheader(f"Image: {img_id}")
            
            # COMMENT SECTION FOR USER
            user_comment = st.text_input("Comment/Issue (optional)", 
                                         value=p.get('comments', {}).get(img_id, {}).get(st.session_state.username, ""),
                                         key=f"comm_{img_id}")

            if st.session_state.use_canvas:
                try:
                    cls = st.selectbox(f"Active Class", p['product_list'], key=f"c_{img_id}")
                    canvas = st_canvas(fill_color="rgba(255,165,0,0.3)", background_image=img,
                                       height=img.height, width=img.width, drawing_mode="rect", key=f"v_{img_id}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button(f"Save & Complete", key=f"s_{img_id}"):
                        if canvas.json_data:
                            objs = canvas.json_data["objects"]
                            anns = [{'class': cls, 'bbox': [o["left"]/img.width + (o["width"]/img.width)/2, 
                                                            o["top"]/img.height + (o["height"]/img.height)/2, 
                                                            o["width"]/img.width, o["height"]/img.height]} 
                                    for o in objs if o["type"] == "rect"]
                            p['annotations'].setdefault(img_id, {})[st.session_state.username] = anns
                            p['statuses'][img_id][st.session_state.username] = "Completed"
                            p.setdefault('comments', {}).setdefault(img_id, {})[st.session_state.username] = user_comment
                            save_projects(projs)
                            st.rerun()
                    
                    if c2.button(f"Flag Image", key=f"f_{img_id}"):
                        p['statuses'][img_id][st.session_state.username] = "Flagged"
                        p.setdefault('comments', {}).setdefault(img_id, {})[st.session_state.username] = user_comment
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
            
            txt = ""
            if id in p['annotations']:
                for u, user_anns in p['annotations'][id].items():
                    if p.get('statuses', {}).get(id, {}).get(u) == "Completed":
                        for a in user_anns:
                            txt += f"{p['product_list'].index(a['class'])} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
            if txt: z.writestr(f"labels/{id}.txt", txt)
    st.download_button("Download ZIP", buf.getvalue(), f"{name}.zip")

if __name__ == "__main__":
    main()
