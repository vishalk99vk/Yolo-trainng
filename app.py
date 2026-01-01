import streamlit as st
import os
import json
import uuid
import zipfile
import hashlib
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# 1. Safe Import & Guard
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS_LIB = True
except ImportError:
    HAS_CANVAS_LIB = False

if not HAS_CANVAS_LIB:
    st.error("Missing dependency: `pip install streamlit-drawable-canvas`")
    st.stop()

# --- CONFIGURATION & PATHS ---
DATA_DIR = "data"
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
ANNOTATIONS_DIR = os.path.join(DATA_DIR, "annotations")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

for d in [DATA_DIR, PROJECTS_DIR, ANNOTATIONS_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def load_json(file_path, default=None):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f: return json.load(f)
    return default if default is not None else {}

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f, indent=4)

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- MAIN APP ---
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
    col1, col2 = st.columns(2)
    with col1:
        u_type = st.selectbox("Account Type", ["user", "admin"])
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        
        if st.button("Login", use_container_width=True):
            users = load_json(USERS_FILE)
            hashed_input = hash_password(u_pass)
            
            # Default Admin Check
            if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            elif u_name in users and users[u_name]['password'] == hashed_input:
                st.session_state.update({"logged_in": True, "user_type": u_type, "username": u_name})
                st.rerun()
            else:
                st.error("Invalid credentials")

# --- ADMIN FUNCTIONS ---
def admin_page():
    st.sidebar.title(f"Admin: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Navigation", ["Projects", "Review", "Users"])

    if menu == "Projects":
        admin_projects_ui()
    elif menu == "Review":
        admin_review_ui()
    elif menu == "Users":
        admin_users_ui()

def admin_projects_ui():
    st.header("Project Management")
    with st.expander("➕ Create New Project"):
        p_name = st.text_input("Project Name")
        prod_file = st.file_uploader("Upload Master Product List (CSV/XLSX)", type=['xlsx', 'csv'])
        if st.button("Create Project") and p_name and prod_file:
            df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
            p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
            proj_data = {
                'product_list': p_list, 
                'images': [], 
                'access_users': [], 
                'assignments': {} # user: [img_ids]
            }
            save_json(os.path.join(PROJECTS_DIR, f"{p_name}.json"), proj_data)
            st.success(f"Project '{p_name}' created.")
            st.rerun()

    available_projects = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
    if not available_projects: return

    sel_p = st.selectbox("Select Project to Manage", available_projects)
    p_path = os.path.join(PROJECTS_DIR, f"{sel_p}.json")
    p = load_json(p_path)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add Content")
        up = st.file_uploader("Upload Images", accept_multiple_files=True)
        if up and st.button("Upload"):
            for f in up:
                id = str(uuid.uuid4())
                img = Image.open(f)
                img.save(os.path.join(IMAGES_DIR, f"{id}.png"))
                p['images'].append({'id': id, 'name': f.name})
            save_json(p_path, p)
            st.success("Images uploaded.")

    with col2:
        st.subheader("Assignments")
        users_list = list(load_json(USERS_FILE).keys())
        target_u = st.selectbox("Assign User Access", users_list)
        if st.button("Grant Access"):
            if target_u not in p['access_users']: 
                p['access_users'].append(target_u)
                save_json(p_path, p)
        
        if p['access_users']:
            u_task = st.selectbox("Assign Task To", p['access_users'])
            assigned_already = p['assignments'].get(u_task, [])
            avail = [i['id'] for i in p['images'] if i['id'] not in assigned_already]
            sel_imgs = st.multiselect("Select Images", avail)
            if st.button("Assign Images") and sel_imgs:
                p['assignments'].setdefault(u_task, []).extend(sel_imgs)
                save_json(p_path, p)
                st.success(f"Assigned {len(sel_imgs)} images.")

    st.divider()
    if st.button("📦 Generate & Download YOLO Dataset"):
        download_yolo(sel_p, p)

def admin_review_ui():
    st.header("Review Data")
    available_projects = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
    if not available_projects: return
    
    sel_p = st.selectbox("Select Project", available_projects)
    p = load_json(os.path.join(PROJECTS_DIR, f"{sel_p}.json"))
    
    user_to_review = st.selectbox("Review User", p['access_users'])
    if user_to_review:
        user_imgs = p['assignments'].get(user_to_review, [])
        if not user_imgs:
            st.info("No images assigned to this user.")
            return
            
        selected_img_id = st.selectbox("Select Image to View", user_imgs)
        ann_path = os.path.join(ANNOTATIONS_DIR, f"{selected_img_id}_{user_to_review}.json")
        
        if os.path.exists(ann_path):
            data = load_json(ann_path)
            img = Image.open(os.path.join(IMAGES_DIR, f"{selected_img_id}.png"))
            draw = ImageDraw.Draw(img)
            for a in data.get('annotations', []):
                xc, yc, w, h = a['bbox']
                l = (xc - w/2) * img.width
                t = (yc - h/2) * img.height
                r = (xc + w/2) * img.width
                b = (yc + h/2) * img.height
                draw.rectangle([l, t, r, b], outline="red", width=5)
                draw.text((l, t-20), a['class'], fill="red")
            st.image(img, caption=f"Status: {data.get('status')}")
        else:
            st.warning("No annotation found for this image yet.")

def admin_users_ui():
    st.subheader("User Management")
    u_acc = load_json(USERS_FILE)
    un = st.text_input("New Username")
    pw = st.text_input("New Password", type="password")
    if st.button("Create User"):
        if un and pw:
            u_acc[un] = {'password': hash_password(pw)}
            save_json(USERS_FILE, u_acc)
            st.success("User created.")

# --- USER FUNCTIONS ---
def user_page():
    st.sidebar.title(f"User: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    
    available_projects = [f.replace(".json", "") for f in os.listdir(PROJECTS_DIR)]
    my_projs = []
    for pn in available_projects:
        conf = load_json(os.path.join(PROJECTS_DIR, f"{pn}.json"))
        if st.session_state.username in conf.get('access_users', []):
            my_projs.append(pn)

    if not my_projs:
        st.info("No projects assigned.")
        return

    sel_p = st.selectbox("Project", my_projs)
    p = load_json(os.path.join(PROJECTS_DIR, f"{sel_p}.json"))
    my_imgs = p['assignments'].get(st.session_state.username, [])

    if not my_imgs:
        st.warning("No images assigned in this project.")
        return

    # Navigation Logic
    if 'img_idx' not in st.session_state: st.session_state.img_idx = 0
    
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("⬅️ Prev") and st.session_state.img_idx > 0:
            st.session_state.img_idx -= 1
            st.rerun()
    with col_nav2:
        st.write(f"Image {st.session_state.img_idx + 1} of {len(my_imgs)}")
    with col_nav3:
        if st.button("Next ➡️") and st.session_state.img_idx < len(my_imgs) - 1:
            st.session_state.img_idx += 1
            st.rerun()

    img_id = my_imgs[st.session_state.img_idx]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    # Load existing annotation if it exists
    ann_path = os.path.join(ANNOTATIONS_DIR, f"{img_id}_{st.session_state.username}.json")
    existing_data = load_json(ann_path, default={'annotations': []})

    if os.path.exists(img_path):
        raw_img = Image.open(img_path).convert("RGB")
        # Resize for Canvas
        canvas_height = 600
        aspect = raw_img.width / raw_img.height
        canvas_width = int(canvas_height * aspect)
        resized_img = raw_img.resize((canvas_width, canvas_height))

        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            st.subheader("Tools")
            sel_cls = st.selectbox("Current Product", p['product_list'])
            st.info("Tip: Draw boxes on the image. All boxes drawn will be saved as the selected product.")
            
            if st.button("💾 Save Annotation", use_container_width=True, variant="primary"):
                st.session_state.save_trigger = True
            
            if st.button("Skip Image", use_container_width=True):
                save_json(ann_path, {"status": "Skipped", "annotations": []})
                st.rerun()

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#e00",
                background_image=resized_img,
                height=canvas_height,
                width=canvas_width,
                drawing_mode="rect",
                key=f"canvas_{img_id}"
            )

        if st.session_state.get("save_trigger"):
            st.session_state.save_trigger = False
            if canvas_result.json_data:
                objs = canvas_result.json_data["objects"]
                yolo_anns = []
                for o in objs:
                    if o["type"] == "rect":
                        # Handle negative widths/heights (drawing backwards)
                        w_abs = abs(o["width"])
                        h_abs = abs(o["height"])
                        left = o["left"] if o["width"] > 0 else o["left"] + o["width"]
                        top = o["top"] if o["height"] > 0 else o["top"] + o["height"]
                        
                        wn, hn = w_abs / canvas_width, h_abs / canvas_height
                        xn = (left / canvas_width) + (wn / 2)
                        yn = (top / canvas_height) + (hn / 2)
                        
                        yolo_anns.append({'class': sel_cls, 'bbox': [xn, yn, wn, hn]})
                
                save_json(ann_path, {"status": "Completed", "annotations": yolo_anns, "timestamp": str(datetime.now())})
                st.success("Saved!")
                st.rerun()

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            img_id = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{img_id}.png")
            
            # Aggregate annotations from all users assigned to this image
            label_text = ""
            has_data = False
            
            for user in p['access_users']:
                ann_path = os.path.join(ANNOTATIONS_DIR, f"{img_id}_{user}.json")
                if os.path.exists(ann_path):
                    data = load_json(ann_path)
                    if data.get('status') == "Completed":
                        has_data = True
                        for a in data['annotations']:
                            idx = p['product_list'].index(a['class'])
                            label_text += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
            
            if has_data:
                z.write(img_p, f"images/{img_id}.png")
                if label_text: z.writestr(f"labels/{img_id}.txt", label_text)
        
        yaml_content = f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images"
        z.writestr("data.yaml", yaml_content)
        
    st.download_button("Download ZIP", buf.getvalue(), f"{name}_yolo_dataset.zip")

if __name__ == "__main__":
    main()
