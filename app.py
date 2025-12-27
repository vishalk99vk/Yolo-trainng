import streamlit as st
import os
import json
import uuid
import zipfile
import base64
from io import BytesIO
import pandas as pd
from PIL import Image

# --- 1. CONFIGURATION & DIRECTORIES ---
DATA_DIR = "data"
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

# --- 2. DATA HELPERS ---
def load_json(f):
    if os.path.exists(f):
        try:
            with open(f, 'r') as file: return json.load(file)
        except: return {}
    return {}

def save_json(f, d):
    with open(f, 'w') as file: json.dump(d, file)

def logout():
    st.session_state.clear()
    st.rerun()

# --- 3. THE "VISIBLE IMAGE" FIX ---
def get_image_base64(img_path, zoom):
    """Loads image, resizes it, and returns a Base64 string for the canvas."""
    img = Image.open(img_path).convert("RGB")
    
    # Calculate dimensions
    h = int(600 * zoom)
    w = int(h * (img.width / img.height))
    
    # Stability cap for wide images
    if w > 1100:
        w = 1100
        h = int(w * (img.height / img.width))
        
    resized_img = img.resize((w, h), Image.Resampling.LANCZOS)
    
    # Convert to Base64
    buffered = BytesIO()
    resized_img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}", w, h

# --- 4. MAIN ROUTER ---
def main():
    st.set_page_config(page_title="YOLO Annotator Pro", layout="wide")
    
    try:
        from streamlit_drawable_canvas import st_canvas
    except ImportError:
        st.error("Missing library: pip install streamlit-drawable-canvas")
        return

    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        login_ui()
    else:
        if st.session_state.user_type == 'admin':
            admin_ui()
        else:
            user_ui()

# --- 5. LOGIN UI ---
def login_ui():
    st.header("🎯 YOLO Labeling System")
    with st.form("login"):
        u_type = st.selectbox("Role", ["user", "admin"])
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In"):
            users = load_json(USERS_FILE)
            if u_type == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            elif u_name in users and users[u_name]['password'] == u_pass:
                st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
                st.rerun()
            else: st.error("Access Denied")

# --- 6. ADMIN PANEL ---
def admin_ui():
    st.sidebar.title("Administrator")
    st.sidebar.button("Logout", on_click=logout)
    menu = st.sidebar.radio("Go to", ["Projects", "Assignments", "Export"])
    projs = load_json(PROJECTS_FILE)
    users_data = load_json(USERS_FILE)

    if menu == "Projects":
        p_name = st.text_input("Project Name")
        p_file = st.file_uploader("Products (CSV/XLSX)", type=['xlsx', 'csv'])
        if st.button("Create Project") and p_name and p_file:
            df = pd.read_csv(p_file) if p_file.name.endswith('.csv') else pd.read_excel(p_file)
            p_list = [str(x).strip() for x in df.iloc[:, 0].dropna().tolist()]
            projs[p_name] = {'product_list': p_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
            save_json(PROJECTS_FILE, projs)
            st.success("Project Created")

    elif menu == "Assignments":
        if not projs: return
        sel_p = st.selectbox("Project", list(projs.keys()))
        p = projs[sel_p]
        up = st.file_uploader("Upload Images", accept_multiple_files=True)
        if up and st.button("Upload"):
            for f in up:
                id = str(uuid.uuid4())
                Image.open(f).save(os.path.join(IMAGES_DIR, f"{id}.png"))
                p['images'].append({'id': id})
            save_json(PROJECTS_FILE, projs)

        st.divider()
        target = st.selectbox("Worker", list(users_data.keys()))
        if st.button("Assign All"):
            p['assignments'][target] = [i['id'] for i in p['images']]
            if target not in p['access_users']: p['access_users'].append(target)
            save_json(PROJECTS_FILE, projs)
            st.success("All images assigned")

    elif menu == "Export":
        sel_p = st.selectbox("Export", list(projs.keys()))
        if st.button("Download ZIP"):
            download_yolo(sel_p, projs[sel_p])

# --- 7. USER PANEL (THE FIX) ---
def user_ui():
    from streamlit_drawable_canvas import st_canvas
    st.sidebar.button("Logout", on_click=logout)
    
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs: st.info("No projects assigned."); return
    p_name = st.selectbox("Project", my_projs)
    p = projs[p_name]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) not in ["Completed", "Skipped"]]
    
    if not pending: st.success("All tasks completed!"); return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        zoom = st.sidebar.slider("Zoom", 0.5, 3.0, 1.0, 0.1)
        
        # --- THE FIX: Load image as Base64 ---
        img_b64, cw, ch = get_image_base64(img_path, zoom)

        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            sel_cls = st.selectbox("Product", p['product_list'], key=f"cls_{img_id}")
            if st.button("Save & Next", use_container_width=True):
                st.session_state[f"sub_{img_id}"] = True
            
            # Forces a clean re-render if browser gets stuck
            if st.button("Reload Image"):
                st.rerun()

        with col_canvas:
            # We use the Base64 data directly in a PIL image wrapper for the component
            bg_image = Image.open(BytesIO(base64.b64decode(img_b64.split(",")[1])))
            
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FF0000",
                background_image=bg_image,
                background_color="#00000000",
                height=ch, 
                width=cw,
                drawing_mode="rect",
                display_toolbar=True,
                key=f"can_{img_id}_{int(zoom*100)}"
            )

        if st.session_state.get(f"sub_{img_id}"):
            if canvas_result.json_data and canvas_result.json_data.get("objects"):
                anns = []
                for o in canvas_result.json_data["objects"]:
                    if o["type"] == "rect":
                        wn, hn = o["width"] / cw, o["height"] / ch
                        xc, yc = (o["left"] / cw) + (wn/2), (o["top"] / ch) + (hn/2)
                        anns.append({'class': sel_cls, 'bbox': [xc, yc, wn, hn]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.session_state[f"sub_{img_id}"] = False
                st.rerun()

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for im in p['images']:
            iid = im['id']
            img_p = os.path.join(IMAGES_DIR, f"{iid}.png")
            if iid in p['annotations'] and os.path.exists(img_p):
                z.write(img_p, f"images/{iid}.png")
                lbl = ""
                for u, ans in p['annotations'][iid].items():
                    if p['statuses'].get(iid, {}).get(u) == "Completed":
                        for a in ans:
                            idx = p['product_list'].index(a['class'])
                            lbl += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                if lbl: z.writestr(f"labels/{iid}.txt", lbl)
        z.writestr("data.yaml", f"names: {p['product_list']}\nnc: {len(p['product_list'])}\ntrain: images\nval: images")
    st.download_button("Download ZIP", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
