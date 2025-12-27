import streamlit as st
import os
import json
import uuid
import zipfile
import base64
from io import BytesIO
import pandas as pd
from PIL import Image

# --- 1. CONFIGURATION & STORAGE ---
DATA_DIR = "data"
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

def load_json(f):
    if os.path.exists(f):
        try:
            with open(f, 'r') as file: return json.load(file)
        except: return {}
    return {}

def save_json(f, d):
    with open(f, 'w') as file: json.dump(d, file)

# --- 2. THE VISIBILITY FIX (BASE64) ---
def get_b64_image(img_path):
    """Converts image to a format the browser MUST display."""
    img = Image.open(img_path).convert("RGB")
    # Resize for stability
    h = 600
    w = int(h * (img.width / img.height))
    if w > 900: 
        w = 900
        h = int(w * (img.height / img.width))
    
    resized = img.resize((w, h), Image.Resampling.LANCZOS)
    buffered = BytesIO()
    resized.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}", w, h

# --- 3. MAIN ROUTER ---
def main():
    st.set_page_config(page_title="YOLO Annotator Final", layout="wide")
    
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        login_ui()
    else:
        if st.session_state.user_type == 'admin':
            admin_ui()
        else:
            user_ui()

def login_ui():
    st.header("🎯 YOLO Object Labeling System")
    with st.form("login"):
        u_name = st.text_input("Username")
        u_pass = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["user", "admin"])
        if st.form_submit_button("Sign In"):
            if role == 'admin' and u_name == 'admin' and u_pass == 'admin':
                st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                st.rerun()
            else:
                users = load_json(USERS_FILE)
                if u_name in users and users[u_name]['password'] == u_pass:
                    st.session_state.update({"logged_in": True, "user_type": 'user', "username": u_name})
                    st.rerun()
                else: st.error("Access Denied")

# --- 4. ADMIN INTERFACE ---
def admin_ui():
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    projs = load_json(PROJECTS_FILE)
    users_data = load_json(USERS_FILE)
    
    tab1, tab2, tab3 = st.tabs(["Projects", "Users/Assign", "Export"])
    
    with tab1:
        p_name = st.text_input("Project Name")
        p_file = st.file_uploader("Class Names (CSV/XLSX)")
        if st.button("Create Project") and p_name and p_file:
            df = pd.read_csv(p_file) if p_file.name.endswith('.csv') else pd.read_excel(p_file)
            projs[p_name] = {'classes': df.iloc[:,0].tolist(), 'images': [], 'assignments': {}, 'annotations': {}, 'status': {}}
            save_json(PROJECTS_FILE, projs); st.success("Created!")

        st.divider()
        if projs:
            sel_p = st.selectbox("Select Project to upload images", list(projs.keys()))
            up = st.file_uploader("Upload Images", accept_multiple_files=True)
            if up and st.button("Save Uploads"):
                for f in up:
                    id = str(uuid.uuid4())
                    Image.open(f).convert("RGB").save(os.path.join(IMAGES_DIR, f"{id}.png"))
                    projs[sel_p]['images'].append(id)
                save_json(PROJECTS_FILE, projs); st.success("Images Saved!")

    with tab2:
        u_n = st.text_input("New Worker Name")
        u_p = st.text_input("New Worker Pass")
        if st.button("Add Worker"):
            users_data[u_n] = {"password": u_p}
            save_json(USERS_FILE, users_data); st.success("Worker Added!")
        
        st.divider()
        if projs and users_data:
            ap = st.selectbox("Assign Project", list(projs.keys()))
            au = st.selectbox("To Worker", list(users_data.keys()))
            if st.button("Assign All Project Images"):
                projs[ap]['assignments'][au] = projs[ap]['images']
                save_json(PROJECTS_FILE, projs); st.success("Assigned!")

    with tab3:
        if projs:
            ep = st.selectbox("Download Project", list(projs.keys()))
            if st.button("Generate YOLO Zip"):
                download_yolo(ep, projs[ep])

# --- 5. USER INTERFACE (THE WHITE SCREEN FIX) ---
def user_ui():
    from streamlit_drawable_canvas import st_canvas
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    
    projs = load_json(PROJECTS_FILE)
    active_p = None
    for n, p in projs.items():
        if st.session_state.username in p.get('assignments', {}):
            active_p = n; break
            
    if not active_p: st.info("No tasks assigned."); return

    p = projs[active_p]
    tasks = p['assignments'][st.session_state.username]
    pending = [i for i in tasks if p['status'].get(i) != "Done"]

    if not pending: st.success("All Done!"); return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    # LOAD STABLE IMAGE
    img_data, w, h = get_b64_image(img_path)

    col1, col2 = st.columns([1, 4])
    with col1:
        st.subheader("Labeling")
        sel_cls = st.selectbox("Object Type", p['classes'])
        if st.button("💾 Save & Next", use_container_width=True):
            st.session_state["submit"] = True

    with col2:
        # THE FIX: We pass the Image object but use a UNIQUE KEY to force a reload
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            stroke_color="#FF0000",
            background_image=Image.open(img_path).convert("RGB").resize((w, h)),
            background_color=None, # IMPORTANT: Setting this to None avoids the white block overlay
            height=h,
            width=w,
            drawing_mode="rect",
            key=f"can_{img_id}", 
            update_freq=500
        )

    if st.session_state.get("submit"):
        if canvas_result.json_data and canvas_result.json_data["objects"]:
            objs = canvas_result.json_data["objects"]
            anns = []
            for o in objs:
                # YOLO Normalization: [class, x_center, y_center, width, height]
                wn, hn = o["width"]/w, o["height"]/h
                xc, yc = (o["left"]/w) + (wn/2), (o["top"]/h) + (hn/2)
                anns.append({"class": sel_cls, "bbox": [xc, yc, wn, hn]})
            
            p['annotations'][img_id] = anns
            p['status'][img_id] = "Done"
            save_json(PROJECTS_FILE, projs)
            st.session_state["submit"] = False
            st.rerun()
        else:
            st.warning("Draw a box first!")
            st.session_state["submit"] = False

# --- 6. EXPORT ---
def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr("classes.txt", "\n".join(p['classes']))
        for iid, anns in p['annotations'].items():
            img_p = os.path.join(IMAGES_DIR, f"{iid}.png")
            if os.path.exists(img_p):
                z.write(img_p, f"images/{iid}.png")
                lbl = ""
                for a in anns:
                    idx = p['classes'].index(a['class'])
                    lbl += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                z.writestr(f"labels/{iid}.txt", lbl)
    st.download_button("Download ZIP", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
