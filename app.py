import streamlit as st
import os
import json
import uuid
import zipfile
import base64
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# 1. Safe Import for Canvas Component
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS_LIB = True
except ImportError:
    HAS_CANVAS_LIB = False

# --- CONFIGURATION & DIRECTORIES ---
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- UTILITIES ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f: return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f)

def get_image_base64(img):
    """Fixes the AttributeError in st_canvas by providing a base64 string"""
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_type' not in st.session_state: st.session_state.user_type = None
if 'username' not in st.session_state: st.session_state.username = None

def logout():
    st.session_state.logged_in = False
    st.rerun()

# --- MAIN APP LOGIC ---
def main():
    st.set_page_config(page_title="YOLO Annotator", layout="wide")
    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_page()
        else:
            user_page()

def login_page():
    st.header("🔑 YOLO Annotation Tool")
    col1, _ = st.columns([1, 1])
    with col1:
        u_type = st.selectbox("Account Type", ["user", "admin"])
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            users = load_json(USERS_FILE)
            if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.logged_in, st.session_state.user_type, st.session_state.username = True, 'admin', 'admin'
                st.rerun()
            elif u_type == 'user' and u_name in users and users[u_name]['password'] == u_pass:
                st.session_state.logged_in, st.session_state.user_type, st.session_state.username = True, 'user', u_name
                st.rerun()
            else:
                st.error("Invalid credentials")

# --- ADMIN PANEL ---
def admin_page():
    st.sidebar.title(f"Admin: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Navigation", ["Manage Projects", "Review Work", "User Accounts"])
    projs = load_json(PROJECTS_FILE)

    if menu == "Manage Projects":
        st.header("Project Management")
        with st.expander("➕ Create New Project"):
            p_name = st.text_input("Project Name")
            prod_file = st.file_uploader("Upload Product Classes (Excel/CSV)", type=['xlsx', 'csv'])
            if st.button("Initialize Project"):
                if p_name and prod_file:
                    df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
                    p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
                    projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
                    save_json(PROJECTS_FILE, projs)
                    st.success(f"Project created with {len(p_list)} classes.")
                    st.rerun()

        if projs:
            sel_p = st.selectbox("Select Project", list(projs.keys()))
            p = projs[sel_p]
            t1, t2, t3 = st.tabs(["Upload Images", "Assignments", "Export Dataset"])
            
            with t1:
                up = st.file_uploader("Upload Raw Images", accept_multiple_files=True, type=['jpg','jpeg','png'])
                if up and st.button("Save Images"):
                    for f in up:
                        id = str(uuid.uuid4())
                        with open(os.path.join(IMAGES_DIR, f"{id}.png"), "wb") as img_f: img_f.write(f.getvalue())
                        p['images'].append({'id': id, 'date': datetime.now().strftime("%Y-%m-%d")})
                    save_json(PROJECTS_FILE, projs)
                    st.success("Uploaded.")

            with t2:
                users_list = list(load_json(USERS_FILE).keys())
                target_u = st.selectbox("Add User Access", users_list)
                if st.button("Grant Access"):
                    if target_u not in p['access_users']: p['access_users'].append(target_u)
                    save_json(PROJECTS_FILE, projs)
                
                if p['access_users']:
                    u_to_assign = st.selectbox("Assign Images to", p['access_users'], key="assign_u")
                    avail = [i['id'] for i in p['images'] if i['id'] not in p['assignments'].get(u_to_assign, [])]
                    sel_imgs = st.multiselect("Select Images", avail)
                    if st.button("Confirm Assignment"):
                        p['assignments'].setdefault(u_to_assign, []).extend(sel_imgs)
                        save_json(PROJECTS_FILE, projs)
                        st.rerun()
            
            with t3:
                if st.button("📦 Download Training Dataset"):
                    download_yolo(sel_p, p)

    elif menu == "Review Work":
        review_ui(projs)

    elif menu == "User Accounts":
        u_acc = load_json(USERS_FILE)
        with st.form("add_user"):
            new_un, new_pw = st.text_input("Username"), st.text_input("Password")
            if st.form_submit_button("Create User"):
                u_acc[new_un] = {'password': new_pw}
                save_json(USERS_FILE, u_acc)
                st.success("User added.")

# --- USER PANEL ---
def user_page():
    st.sidebar.title(f"User: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs:
        st.info("No assignments.")
        return

    sel_p = st.selectbox("Select Project", my_projs)
    p = projs[sel_p]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) != "Completed"]
    
    if not pending:
        st.success("All tasks complete!")
        return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        img = Image.open(img_path)
        bg_url = get_image_base64(img) # Fix for AttributeError
        
        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            sel_cls = st.selectbox("Class", p['product_list'], key=f"cls_{img_id}")
            if st.button("🚀 Submit Annotation", use_container_width=True):
                st.session_state[f"save_{img_id}"] = True

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                background_image=bg_url,
                height=img.height, width=img.width,
                drawing_mode="rect", key=f"canvas_{img_id}"
            )

        if st.session_state.get(f"save_{img_id}"):
            if canvas_result.json_data:
                objs = canvas_result.json_data["objects"]
                yolo_anns = []
                for o in objs:
                    if o["type"] == "rect":
                        w_n, h_n = o["width"] / img.width, o["height"] / img.height
                        yolo_anns.append({'class': sel_cls, 'bbox': [(o["left"]/img.width)+(w_n/2), (o["top"]/img.height)+(h_n/2), w_n, h_n]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.rerun()

def review_ui(projs):
    st.header("Work Review")
    if not projs: return
    sel_p = st.selectbox("Project", list(projs.keys()))
    p = projs[sel_p]
    for u in p['access_users']:
        with st.expander(f"User: {u}"):
            for img_id in p['assignments'].get(u, []):
                if img_id in p['annotations'] and u in p['annotations'][img_id]:
                    img = Image.open(os.path.join(IMAGES_DIR, f"{img_id}.png")).convert("RGB")
                    draw = ImageDraw.Draw(img)
                    for ann in p['annotations'][img_id][u]:
                        xc, yc, w, h = ann['bbox']
                        l, t = (xc - w/2) * img.width, (yc - h/2) * img.height
                        r, b = (xc + w/2) * img.width, (yc + h/2) * img.height
                        draw.rectangle([l, t, r, b], outline="red", width=3)
                    st.image(img, use_container_width=True)

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            id = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{id}.png")
            if os.path.exists(img_p): z.write(img_p, f"images/{id}.png")
            
            label_text = ""
            if id in p['annotations']:
                for user, anns in p['annotations'][id].items():
                    if p.get('statuses', {}).get(id, {}).get(user) == "Completed":
                        for a in anns:
                            idx = p['product_list'].index(a['class'])
                            label_text += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
            if label_text: z.writestr(f"labels/{id}.txt", label_text)
        
        yaml = f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images"
        z.writestr("data.yaml", yaml)
    st.download_button("💾 Download ZIP", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
