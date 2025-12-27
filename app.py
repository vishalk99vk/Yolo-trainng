import streamlit as st
import os, json, uuid, zipfile, pandas as pd
from io import BytesIO
from PIL import Image

# --- 1. SETTINGS & PATHS ---
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

# --- 2. AUTHENTICATION ---
def main():
    st.set_page_config(page_title="YOLO Annotator Pro", layout="wide")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🎯 YOLO Labeling System")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["user", "admin"])
            if st.form_submit_button("Sign In"):
                if role == 'admin' and u == 'admin' and p == 'admin':
                    st.session_state.update({"logged_in": True, "user_type": 'admin', "username": 'admin'})
                    st.rerun()
                else:
                    users = load_json(USERS_FILE)
                    if u in users and users[u]['password'] == p:
                        st.session_state.update({"logged_in": True, "user_type": 'user', "username": u})
                        st.rerun()
                    else: st.error("Invalid credentials")
    else:
        if st.session_state.user_type == 'admin': admin_ui()
        else: user_ui()

# --- 3. ADMIN PANEL ---
def admin_ui():
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    projs = load_json(PROJECTS_FILE)
    users_data = load_json(USERS_FILE)
    
    menu = st.sidebar.radio("Menu", ["Projects", "Users", "Export"])

    if menu == "Projects":
        p_name = st.text_input("Project Name")
        p_file = st.file_uploader("Class List (CSV/XLSX)")
        if st.button("Create") and p_name and p_file:
            df = pd.read_csv(p_file) if p_file.name.endswith('.csv') else pd.read_excel(p_file)
            projs[p_name] = {'classes': df.iloc[:,0].tolist(), 'images': [], 'assignments': {}, 'annotations': {}, 'status': {}}
            save_json(PROJECTS_FILE, projs); st.success("Project Created")

        st.divider()
        if projs:
            sel_p = st.selectbox("Add Images to", list(projs.keys()))
            up = st.file_uploader("Upload Images", accept_multiple_files=True)
            if up and st.button("Upload"):
                for f in up:
                    id = str(uuid.uuid4())
                    Image.open(f).convert("RGB").save(os.path.join(IMAGES_DIR, f"{id}.png"))
                    projs[sel_p]['images'].append(id)
                save_json(PROJECTS_FILE, projs); st.success("Images Uploaded")

    elif menu == "Users":
        un = st.text_input("Worker Username")
        up = st.text_input("Worker Password")
        if st.button("Create User"):
            users_data[un] = {"password": up}
            save_json(USERS_FILE, users_data); st.success("User Created")
        
        st.divider()
        if projs and users_data:
            ap = st.selectbox("Assign Project", list(projs.keys()))
            au = st.selectbox("Worker", list(users_data.keys()))
            if st.button("Assign All Images"):
                projs[ap]['assignments'][au] = projs[ap]['images']
                save_json(PROJECTS_FILE, projs); st.success("Task Assigned")

    elif menu == "Export":
        if projs:
            ep = st.selectbox("Export", list(projs.keys()))
            if st.button("Download ZIP"): download_yolo(ep, projs[ep])

# --- 4. USER PANEL (THE STABILITY FIX) ---
def user_ui():
    from streamlit_drawable_canvas import st_canvas
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    
    projs = load_json(PROJECTS_FILE)
    active_p = None
    for n, p in projs.items():
        if st.session_state.username in p.get('assignments', {}):
            active_p = n; break
            
    if not active_p: st.info("No projects assigned."); return

    p = projs[active_p]
    tasks = p['assignments'][st.session_state.username]
    # FIXED: Ensure "status" key exists to prevent KeyError
    if 'status' not in p: p['status'] = {}
    pending = [i for i in tasks if p['status'].get(i) != "Done"]

    if not pending: st.success("All tasks completed!"); return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")

    # LOAD & RESIZE
    img = Image.open(img_path).convert("RGB")
    h = 600
    w = int(h * (img.width / img.height))
    if w > 900: w = 900; h = int(w * (img.height / img.width))
    display_img = img.resize((w, h), Image.Resampling.LANCZOS)

    col1, col2 = st.columns([1, 4])
    with col1:
        st.subheader("Tools")
        sel_cls = st.selectbox("Product", p['classes'], key=f"cls_{img_id}")
        if st.button("💾 Save & Next", use_container_width=True):
            st.session_state["do_save"] = True

    with col2:
        try:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FF0000",
                background_image=display_img,
                background_color=None, # Removes white overlay
                height=h,
                width=w,
                drawing_mode="rect",
                key=f"can_{img_id}", # Unique key per image
                update_freq=500
            )
        except Exception as e:
            st.error("Canvas failed to load. Try refreshing your browser.")
            st.stop()

    if st.session_state.get("do_save"):
        if canvas_result.json_data and canvas_result.json_data["objects"]:
            objs = canvas_result.json_data["objects"]
            anns = []
            for o in objs:
                # YOLO Format Calculation
                wn, hn = o["width"]/w, o["height"]/h
                xc, yc = (o["left"]/w) + (wn/2), (o["top"]/h) + (hn/2)
                anns.append({"class": sel_cls, "bbox": [xc, yc, wn, hn]})
            
            p.setdefault('annotations', {})[img_id] = anns
            p['status'][img_id] = "Done"
            save_json(PROJECTS_FILE, projs)
            st.session_state["do_save"] = False
            st.rerun()
        else:
            st.warning("Please draw a box first!")
            st.session_state["do_save"] = False

# --- 5. DATA EXPORT ---
def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr("classes.txt", "\n".join(p['classes']))
        for iid, anns in p.get('annotations', {}).items():
            img_p = os.path.join(IMAGES_DIR, f"{iid}.png")
            if os.path.exists(img_p):
                z.write(img_p, f"images/{iid}.png")
                lbl = ""
                for a in anns:
                    idx = p['classes'].index(a['class'])
                    lbl += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                z.writestr(f"labels/{iid}.txt", lbl)
    st.download_button("Download Dataset", buf.getvalue(), f"{name}_yolo.zip")

if __name__ == "__main__":
    main()
