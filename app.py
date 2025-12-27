import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# Safe Import for Canvas
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS_LIB = True
except ImportError:
    HAS_CANVAS_LIB = False

# --- CONFIGURATION ---
DATA_DIR = "data"
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- HELPERS ---
def load_json(f):
    return json.load(open(f, 'r')) if os.path.exists(f) else {}

def save_json(f, d):
    with open(f, 'w') as file: json.dump(d, file)

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- APP ---
def main():
    st.set_page_config(page_title="YOLO Searchable Tagger", layout="wide")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        login_ui()
    else:
        if st.session_state.user_type == 'admin':
            admin_ui()
        else:
            user_ui()

def login_ui():
    st.header("🔑 YOLO Annotation System")
    with st.form("login"):
        u_type = st.selectbox("Role", ["user", "admin"])
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            users = load_json(USERS_FILE)
            if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            elif u_type == 'user' and u_name in users and users[u_name]['password'] == u_pass:
                st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
                st.rerun()
            else: st.error("Access Denied")

def user_ui():
    st.sidebar.title(f"User: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs:
        st.info("No projects assigned.")
        return

    p_name = st.selectbox("Project", my_projs)
    p = projs[p_name]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) not in ["Completed", "Skipped"]]
    
    if not pending:
        st.success("All tasks complete!")
        return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        raw_img = Image.open(img_path).convert("RGB")
        
        # --- UI CONTROLS ---
        st.sidebar.subheader("Canvas Tools")
        zoom_scale = st.sidebar.slider("Zoom Level", 0.5, 3.0, 1.0, 0.1)
        drawing_mode = st.sidebar.selectbox("Tool", ("rect", "transform"))
        
        base_h = 600
        canvas_h = int(base_h * zoom_scale)
        aspect = raw_img.width / raw_img.height
        canvas_w = int(canvas_h * aspect)
        resized_img = raw_img.resize((canvas_w, canvas_h))
        
        initial_drawing = st.session_state.get(f"draft_{img_id}", None)

        col_ui, col_canvas = st.columns([1, 4])
        
        with col_ui:
            st.markdown("### Manual Tagging")
            # SEARCHABLE DROPDOWN
            sel_cls = st.selectbox(
                "Search & Select Product", 
                p['product_list'], 
                index=0,
                placeholder="Type to search...",
                key=f"search_{img_id}"
            )
            
            st.write("---")
            if st.button("🚀 Save Image", use_container_width=True):
                st.session_state[f"sub_{img_id}"] = True
            
            if st.button("⏭️ Skip Image", use_container_width=True):
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Skipped"
                save_json(PROJECTS_FILE, projs)
                st.rerun()

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FF0000",
                background_image=resized_img,
                height=canvas_h,
                width=canvas_w,
                drawing_mode=drawing_mode,
                initial_drawing=initial_drawing,
                display_toolbar=True,
                update_freq=500,
                key=f"can_{img_id}"
            )

            # Auto-save current progress
            if canvas_result.json_data is not None:
                st.session_state[f"draft_{img_id}"] = canvas_result.json_data

        if st.session_state.get(f"sub_{img_id}"):
            if canvas_result.json_data and len(canvas_result.json_data["objects"]) > 0:
                objs = canvas_result.json_data["objects"]
                yolo_anns = []
                for o in objs:
                    if o["type"] == "rect":
                        wn, hn = o["width"] / canvas_w, o["height"] / canvas_h
                        xc = (o["left"] / canvas_w) + (wn / 2)
                        yc = (o["top"] / canvas_h) + (hn / 2)
                        # We use the index of the selected product for YOLO
                        yolo_anns.append({'class': sel_cls, 'bbox': [xc, yc, wn, hn]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                del st.session_state[f"draft_{img_id}"]
                del st.session_state[f"sub_{img_id}"]
                st.rerun()
            else:
                st.warning("Draw a box first!")
                st.session_state[f"sub_{img_id}"] = False

# --- ADMIN PANEL ---
def admin_ui():
    st.sidebar.title("Admin Panel")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Menu", ["Projects", "Review & Export"])
    projs = load_json(PROJECTS_FILE)

    if menu == "Projects":
        p_name = st.text_input("Project Name")
        prod_file = st.file_uploader("Upload Master List (Excel/CSV)", type=['xlsx', 'csv'])
        if st.button("Create") and p_name and prod_file:
            df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
            p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
            projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
            save_json(PROJECTS_FILE, projs)
            st.success("Project Created")
            
    elif menu == "Review & Export":
        if projs:
            sel_p = st.selectbox("Select Project", list(projs.keys()))
            p = projs[sel_p]
            up = st.file_uploader("Upload Images", accept_multiple_files=True)
            if up and st.button("Upload"):
                for f in up:
                    id = str(uuid.uuid4())
                    Image.open(f).save(os.path.join(IMAGES_DIR, f"{id}.png"))
                    p['images'].append({'id': id})
                save_json(PROJECTS_FILE, projs)
            
            if st.button("📥 Export YOLO Dataset"):
                download_yolo(sel_p, p)

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            iid = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{iid}.png")
            if iid in p['annotations'] and os.path.exists(img_p):
                z.write(img_p, f"images/{iid}.png")
                labels = ""
                for u, anns in p['annotations'][iid].items():
                    if p['statuses'][iid][u] == "Completed":
                        for a in anns:
                            idx = p['product_list'].index(a['class'])
                            labels += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                if labels: z.writestr(f"labels/{iid}.txt", labels)
        z.writestr("data.yaml", f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images")
    st.download_button("Download ZIP", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
