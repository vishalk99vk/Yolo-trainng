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

# --- CONFIGURATION ---
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- HELPER FUNCTIONS ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f: return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f)

def logout():
    st.session_state.logged_in = False
    st.rerun()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="YOLO Annotator", layout="wide")
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
    u_type = st.selectbox("Account Type", ["user", "admin"])
    u_name = st.text_input("Username")
    u_pass = st.text_input("Password", type="password")
    if st.button("Login"):
        users = load_json(USERS_FILE)
        if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
            st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
            st.rerun()
        elif u_type == 'user' and u_name in users and users[u_name]['password'] == u_pass:
            st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
            st.rerun()
        else:
            st.error("Invalid credentials")

# --- ADMIN FUNCTIONS ---
def admin_page():
    st.sidebar.title(f"Admin: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Navigation", ["Projects", "Review", "Users"])
    projs = load_json(PROJECTS_FILE)

    if menu == "Projects":
        with st.expander("➕ Create New Project"):
            p_name = st.text_input("Project Name")
            st.info("The Excel/CSV uploaded here defines the products for ALL images in this project.")
            prod_file = st.file_uploader("Upload Master Product List", type=['xlsx', 'csv'])
            if st.button("Create Project") and p_name and prod_file:
                df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
                # Take first column as the class list
                p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
                projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
                save_json(PROJECTS_FILE, projs)
                st.success(f"Project '{p_name}' created with {len(p_list)} products.")
                st.rerun()

        if projs:
            st.divider()
            sel_p = st.selectbox("Select Project to Manage", list(projs.keys()))
            p = projs[sel_p]
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Loaded Products:** {len(p['product_list'])}")
                up = st.file_uploader("Add Images to this Project", accept_multiple_files=True)
                if up and st.button("Upload Images"):
                    for f in up:
                        id = str(uuid.uuid4())
                        Image.open(f).save(os.path.join(IMAGES_DIR, f"{id}.png"))
                        p['images'].append({'id': id})
                    save_json(PROJECTS_FILE, projs)
                    st.success("Images added.")
            
            with col2:
                u_list = list(load_json(USERS_FILE).keys())
                target_u = st.selectbox("Assign User Access", u_list)
                if st.button("Grant Access"):
                    if target_u not in p['access_users']: p['access_users'].append(target_u)
                    save_json(PROJECTS_FILE, projs)
                
                if p['access_users']:
                    u_task = st.selectbox("Assign Task To", p['access_users'])
                    avail = [i['id'] for i in p['images'] if i['id'] not in p['assignments'].get(u_task, [])]
                    sel_imgs = st.multiselect("Select Images", avail)
                    if st.button("Assign Images") and sel_imgs:
                        p['assignments'].setdefault(u_task, []).extend(sel_imgs)
                        save_json(PROJECTS_FILE, projs)
            
            st.divider()
            if st.button("📦 Download Final YOLO Dataset"):
                download_yolo(sel_p, p)

    elif menu == "Review":
        review_ui(projs)
    
    elif menu == "Users":
        u_acc = load_json(USERS_FILE)
        un, pw = st.text_input("Username"), st.text_input("Password")
        if st.button("Add User Account"):
            u_acc[un] = {'password': pw}
            save_json(USERS_FILE, u_acc)

# --- USER FUNCTIONS ---
def user_page():
    st.sidebar.button("Logout", on_click=logout)
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs:
        st.info("No projects assigned to you.")
        return

    p_name = st.selectbox("Current Project", my_projs)
    p = projs[p_name]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) not in ["Completed", "Skipped"]]
    
    st.write(f"📂 **Project:** {p_name} | **Pending:** {len(pending)}")

    if not pending:
        st.success("All assigned images completed!")
        return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        raw_img = Image.open(img_path).convert("RGB")
        
        # Consistent resizing logic
        canvas_height = 600
        aspect_ratio = raw_img.width / raw_img.height
        canvas_width = int(canvas_height * aspect_ratio)
        resized_img = raw_img.resize((canvas_width, canvas_height))
        
        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            st.subheader("Annotation")
            # This list is identical for ALL images in this project
            sel_cls = st.selectbox("Select Product", p['product_list'], key=f"c_{img_id}")
            
            if st.button("✅ Save & Next", use_container_width=True):
                st.session_state[f"act_{img_id}"] = "save"
            
            st.write("---")
            if st.button("⏭️ Skip / Missing", use_container_width=True):
                st.session_state[f"act_{img_id}"] = "skip"

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                background_image=resized_img,
                height=canvas_height,
                width=canvas_width,
                drawing_mode="rect",
                key=f"can_{img_id}"
            )

        action = st.session_state.get(f"act_{img_id}")
        if action == "save":
            if canvas_result.json_data:
                objs = canvas_result.json_data["objects"]
                yolo_anns = []
                for o in objs:
                    if o["type"] == "rect":
                        wn, hn = o["width"] / canvas_width, o["height"] / canvas_height
                        # Map back to normalized YOLO coordinates
                        yolo_anns.append({'class': sel_cls, 'bbox': [(o["left"]/canvas_width)+(wn/2), (o["top"]/canvas_height)+(hn/2), wn, hn]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.session_state[f"act_{img_id}"] = None
                st.rerun()
                
        elif action == "skip":
            p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Skipped"
            save_json(PROJECTS_FILE, projs)
            st.session_state[f"act_{img_id}"] = None
            st.rerun()

def review_ui(projs):
    st.header("Review Data")
    sel_p = st.selectbox("Select Project", list(projs.keys()))
    p = projs[sel_p]
    for u in p['access_users']:
        with st.expander(f"Review: {u}"):
            for iid in p['assignments'].get(u, []):
                stat = p.get('statuses', {}).get(iid, {}).get(u, "Pending")
                if stat == "Completed":
                    img = Image.open(os.path.join(IMAGES_DIR, f"{iid}.png"))
                    draw = ImageDraw.Draw(img)
                    for a in p['annotations'][iid][u]:
                        xc, yc, w, h = a['bbox']
                        l, t = (xc - w/2) * img.width, (yc - h/2) * img.height
                        r, b = (xc + w/2) * img.width, (yc + h/2) * img.height
                        draw.rectangle([l,t,r,b], outline="red", width=5)
                    st.image(img, caption=f"ID: {iid}")

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            id = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{id}.png")
            if os.path.exists(img_p):
                label_text = ""
                is_valid = False
                if id in p['annotations']:
                    for u, anns in p['annotations'][id].items():
                        if p['statuses'][id][u] == "Completed":
                            is_valid = True
                            for a in anns:
                                # Standard YOLO: Class Index (0, 1, 2...)
                                idx = p['product_list'].index(a['class'])
                                label_text += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                
                if is_valid:
                    z.write(img_p, f"images/{id}.png")
                    if label_text: z.writestr(f"labels/{id}.txt", label_text)
        
        yaml_data = f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images"
        z.writestr("data.yaml", yaml_data)
    st.download_button("Download Dataset", buf.getvalue(), f"{name}_dataset.zip")

if __name__ == "__main__":
    main()
