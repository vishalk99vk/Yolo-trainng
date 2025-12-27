import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image

# --- CONFIGURATION ---
DATA_DIR = "data"
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- DATABASE HELPERS ---
def load_json(f):
    try:
        if os.path.exists(f):
            with open(f, 'r') as file: return json.load(file)
    except: return {}
    return {}

def save_json(f, d):
    with open(f, 'w') as file: json.dump(d, file)

def logout():
    st.session_state.clear()
    st.rerun()

# --- MAIN ROUTER ---
def main():
    st.set_page_config(page_title="YOLO Annotator Safe-Mode", layout="wide")
    
    # Ensure canvas is imported
    try:
        from streamlit_drawable_canvas import st_canvas
    except ImportError:
        st.error("Run: pip install streamlit-drawable-canvas")
        return

    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        login_ui()
    else:
        if st.session_state.user_type == 'admin':
            admin_ui()
        else:
            user_ui()

# --- LOGIN ---
def login_ui():
    st.header("📦 Product Tagger")
    with st.form("login"):
        u_type = st.selectbox("Role", ["user", "admin"])
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            users = load_json(USERS_FILE)
            if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            elif u_name in users and users[u_name]['password'] == u_pass:
                st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
                st.rerun()
            else: st.error("Invalid credentials")

# --- ADMIN PANEL ---
def admin_ui():
    st.sidebar.title("Admin")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Go to", ["Projects", "Assignments", "Export"])
    
    projs = load_json(PROJECTS_FILE)
    users_data = load_json(USERS_FILE)

    if menu == "Projects":
        st.subheader("Create Project")
        p_name = st.text_input("Project Name")
        prod_file = st.file_uploader("Upload Product List (Excel/CSV)", type=['csv', 'xlsx'])
        if st.button("Create") and p_name and prod_file:
            df = pd.read_csv(prod_file) if prod_file.name.endswith('.csv') else pd.read_excel(prod_file)
            p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
            projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
            save_json(PROJECTS_FILE, projs)
            st.success("Project Created")
        
        st.divider()
        st.subheader("Add User")
        un, pw = st.text_input("User"), st.text_input("Pass")
        if st.button("Add User") and un and pw:
            users_data[un] = {"password": pw}
            save_json(USERS_FILE, users_data)

    elif menu == "Assignments":
        if not projs: return
        sel_p = st.selectbox("Select Project", list(projs.keys()))
        p = projs[sel_p]
        
        up = st.file_uploader("Upload Images", accept_multiple_files=True)
        if up and st.button("Save Images"):
            for f in up:
                id = str(uuid.uuid4())
                Image.open(f).save(os.path.join(IMAGES_DIR, f"{id}.png"))
                p['images'].append({'id': id})
            save_json(PROJECTS_FILE, projs)

        st.divider()
        all_assigned = []
        for u in p['assignments']: all_assigned.extend(p['assignments'][u])
        avail = [im['id'] for im in p['images'] if im['id'] not in all_assigned]
        
        if avail:
            target_u = st.selectbox("Assign to Worker", list(users_data.keys()))
            num = st.number_input("Count", 1, len(avail), min(10, len(avail)))
            if st.button("Confirm Bulk Assignment"):
                if target_u not in p['access_users']: p['access_users'].append(target_u)
                p['assignments'].setdefault(target_u, []).extend(avail[:num])
                save_json(PROJECTS_FILE, projs)
                st.rerun()

    elif menu == "Export":
        sel_p = st.selectbox("Export", list(projs.keys()))
        if st.button("Download ZIP"):
            download_yolo(sel_p, projs[sel_p])

# --- USER PANEL (CRASH-PROOFED) ---
def user_ui():
    from streamlit_drawable_canvas import st_canvas
    st.sidebar.button("Logout", on_click=logout)
    
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs: st.info("No tasks."); return
    p_name = st.selectbox("Project", my_projs)
    p = projs[p_name]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) not in ["Completed", "Skipped"]]
    
    if not pending: st.success("All Done!"); return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        # RESIZE IMAGE
        raw_img = Image.open(img_path).convert("RGB")
        zoom = st.sidebar.slider("Zoom", 0.5, 2.0, 1.0, 0.1)
        canvas_h = int(600 * zoom)
        canvas_w = int(canvas_h * (raw_img.width / raw_img.height))
        resized_img = raw_img.resize((canvas_w, canvas_h))
        
        # SAFE INITIAL DRAWING
        # Python 3.13 Crash Fix: Ensure initial_drawing is never a malformed object
        init_draw = st.session_state.get(f"draft_{img_id}")
        if not isinstance(init_draw, dict) or "objects" not in init_draw:
            init_draw = None

        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            sel_cls = st.selectbox("Product", p['product_list'], key=f"sel_{img_id}")
            if st.button("Save & Next", use_container_width=True):
                st.session_state[f"sub_{img_id}"] = True
            if st.button("Skip", use_container_width=True):
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Skipped"
                save_json(PROJECTS_FILE, projs)
                st.rerun()

        with col_canvas:
            # UNIQUE KEY PER IMAGE TO PREVENT CACHE ERRORS
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FF0000",
                background_image=resized_img,
                height=canvas_h, width=canvas_w,
                drawing_mode="rect",
                initial_drawing=init_draw,
                display_toolbar=True,
                update_freq=1000,
                key=f"canvas_img_{img_id}"
            )
            # Auto-save current state
            if canvas_result.json_data:
                st.session_state[f"draft_{img_id}"] = canvas_result.json_data

        if st.session_state.get(f"sub_{img_id}"):
            if canvas_result.json_data and canvas_result.json_data.get("objects"):
                yolo_anns = []
                for o in canvas_result.json_data["objects"]:
                    if o["type"] == "rect":
                        wn, hn = o["width"] / canvas_w, o["height"] / canvas_h
                        xc, yc = (o["left"] / canvas_w) + (wn/2), (o["top"] / canvas_h) + (hn/2)
                        yolo_anns.append({'class': sel_cls, 'bbox': [xc, yc, wn, hn]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.session_state.pop(f"draft_{img_id}", None)
                st.session_state.pop(f"sub_{img_id}", None)
                st.rerun()
            else: st.warning("Draw a box first!")

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
                    if p['statuses'].get(iid, {}).get(u) == "Completed":
                        for a in anns:
                            idx = p['product_list'].index(a['class'])
                            labels += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                if labels: z.writestr(f"labels/{iid}.txt", labels)
        z.writestr("data.yaml", f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images")
    st.download_button("Download Now", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
